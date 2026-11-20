"""ElevenLabs Scribe v3 Live realtime adapter (server-side, VAD commit mode).

Message shapes follow the official API reference (see docs/live/scribe-preflight.md).
The adapter never logs or includes the API key, transcript text or audio in errors.
"""

import asyncio
import base64
import contextlib
import json
import math
from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from ..audio_ai_ports import ScribeNotice, TimedToken

SCRIBE_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
MODEL_ID = "scribe_v3_live"
AUDIO_FORMAT = "pcm_16000"
SAMPLE_RATE = 16000
CONNECT_TIMEOUT_SECS = 10.0
CLOSE_TIMEOUT_SECS = 2.0

# Documented error message_type values (API reference: ScribeError and siblings).
FATAL_ERRORS = frozenset({"auth_error", "quota_exceeded", "unaccepted_terms", "invalid_request"})
TRANSIENT_ERRORS = frozenset(
    {
        "error",
        "input_error",  # usually our bug; A should retry once, then stop
        "commit_throttled",
        "rate_limited",
        "queue_overflow",
        "resource_exhausted",
        "session_time_limit_exceeded",
        "chunk_size_exceeded",
        "insufficient_audio_activity",
        "transcriber_error",
    }
)

_END = object()


class ScribeSetupError(Exception):
    """Raised by open(); `fatal` tells A whether to stop retrying."""

    def __init__(self, code: str, fatal: bool) -> None:
        super().__init__(code)
        self.code = code
        self.fatal = fatal


class ScribeClosedError(ConnectionError):
    """send_pcm after the upstream connection ended or the stream was closed."""


def seconds_to_samples(seconds: Any) -> int | None:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        return None
    return round(seconds * SAMPLE_RATE)


def _tokens(words: Any) -> tuple[TimedToken, ...]:
    out: list[TimedToken] = []
    if not isinstance(words, list):
        return ()
    for w in words:
        if not isinstance(w, Mapping) or w.get("type", "word") != "word":
            continue  # spacing / audio_event items are not words
        text = w.get("text")
        start, end = seconds_to_samples(w.get("start")), seconds_to_samples(w.get("end"))
        if not isinstance(text, str) or start is None or end is None:
            continue  # never fabricate timing
        out.append(TimedToken(text=text, start_sample=start, end_sample=end))
    return tuple(out)


def _lang(msg: Mapping[str, Any]) -> str | None:
    value = msg.get("language_code")
    return value if isinstance(value, str) else None


def classify_error(kind: str, epoch: int) -> ScribeNotice:
    fatal = kind in FATAL_ERRORS
    return ScribeNotice(
        epoch=epoch,
        kind="fatal_error" if fatal else "transient_error",
        code=kind,
        message=f"Scribe reported {kind}",  # provider detail text deliberately not forwarded
    )


class _Normalizer:
    """Maps one provider JSON object to zero or one notice."""

    def __init__(self, epoch: int) -> None:
        self.epoch = epoch
        self._last_partial: str | None = None

    def handle(self, msg: Any) -> ScribeNotice | None:
        if not isinstance(msg, Mapping):
            return None
        kind = msg.get("message_type")
        text = msg.get("text")
        if kind == "partial_transcript":
            if not isinstance(text, str) or not text.strip() or text == self._last_partial:
                return None  # keepalive / unchanged partial
            self._last_partial = text
            return ScribeNotice(epoch=self.epoch, kind="partial", text=text, language_code=_lang(msg))
        if kind == "committed_transcript":
            self._last_partial = None
            if not isinstance(text, str):
                return None
            return ScribeNotice(epoch=self.epoch, kind="commit", text=text, language_code=_lang(msg))
        if kind == "committed_transcript_with_timestamps":
            if not isinstance(text, str):
                return None
            return ScribeNotice(
                epoch=self.epoch,
                kind="timed",
                text=text,
                language_code=_lang(msg),
                tokens=_tokens(msg.get("words")),
                timestamp_basis="unknown",
            )
        if isinstance(kind, str) and (kind in FATAL_ERRORS or kind in TRANSIENT_ERRORS):
            return classify_error(kind, self.epoch)
        if isinstance(kind, str) and kind.endswith("_error"):
            return classify_error("error", self.epoch)
        return None  # session_started, warning, diarization etc. are ignored


class ElevenLabsScribeStream:
    def __init__(self, ws: Any, epoch: int) -> None:
        self._ws = ws
        self._epoch = epoch
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._closed = False
        self._ended = False
        self._reader = asyncio.ensure_future(self._read())

    def _finish(self) -> None:
        if not self._ended:
            self._ended = True
            self._queue.put_nowait(_END)

    def _closed_notice(self, code: Any) -> None:
        if not self._closed:
            self._queue.put_nowait(
                ScribeNotice(
                    epoch=self._epoch,
                    kind="transient_error",
                    code="upstream_closed",
                    message=f"Scribe connection closed (code {code})",
                )
            )

    async def _read(self) -> None:
        norm = _Normalizer(self._epoch)
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    notice = norm.handle(json.loads(raw))
                except ValueError:
                    continue
                if notice is not None:
                    self._queue.put_nowait(notice)
                    if notice.kind == "fatal_error":
                        return
            self._closed_notice(getattr(self._ws, "close_code", None))
        except ConnectionClosed as exc:
            self._closed_notice(exc.rcvd.code if exc.rcvd else "none")
        except Exception:  # noqa: BLE001 - report generically; never leak payloads
            if not self._closed:
                self._queue.put_nowait(
                    ScribeNotice(
                        epoch=self._epoch,
                        kind="transient_error",
                        code="upstream_read_failed",
                        message="Scribe read failed",
                    )
                )
        finally:
            self._finish()

    async def send_pcm(self, pcm_s16le: bytes) -> None:
        if self._closed or self._ended:
            raise ScribeClosedError("Scribe stream is closed")
        if len(pcm_s16le) % 2:
            raise ValueError("PCM must be whole 16-bit samples")
        if not pcm_s16le:
            return
        payload = json.dumps(
            {
                "message_type": "input_audio_chunk",
                "audio_base_64": base64.b64encode(pcm_s16le).decode("ascii"),
                "commit": False,
                "sample_rate": SAMPLE_RATE,
            }
        )
        try:
            await self._ws.send(payload)
        except ConnectionClosed as exc:
            raise ScribeClosedError("Scribe connection closed") from exc

    async def events(self) -> AsyncIterator[ScribeNotice]:
        while True:
            item = await self._queue.get()
            if item is _END:
                self._queue.put_nowait(_END)  # keep later iterations terminating
                return
            yield item

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._ws.close(), CLOSE_TIMEOUT_SECS)
        finally:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
            self._finish()


class ElevenLabsScribeAdapter:
    def __init__(self, *, api_key: str, vad_silence_secs: float, url: str = SCRIBE_URL) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._vad = vad_silence_secs
        self._url = url

    def _query(self) -> str:
        return urlencode(
            {
                "model_id": MODEL_ID,  # explicit: API default is a different model
                "audio_format": AUDIO_FORMAT,
                "commit_strategy": "vad",
                "vad_silence_threshold_secs": self._vad,
                "include_timestamps": "true",
            }
        )

    async def open(self, epoch: int) -> ElevenLabsScribeStream:
        try:
            ws = await websockets.connect(
                f"{self._url}?{self._query()}",
                additional_headers={"xi-api-key": self._api_key},
                open_timeout=CONNECT_TIMEOUT_SECS,
                close_timeout=CLOSE_TIMEOUT_SECS,
                max_size=2**22,
            )
        except InvalidStatus as exc:
            status = exc.response.status_code
            raise ScribeSetupError(f"http_{status}", status in (401, 402, 403)) from None
        except (OSError, TimeoutError, websockets.exceptions.WebSocketException) as exc:
            raise ScribeSetupError(f"connect_failed_{type(exc).__name__}", False) from None
        return ElevenLabsScribeStream(ws, epoch)

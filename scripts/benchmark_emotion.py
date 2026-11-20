#!/usr/bin/env python3
"""Benchmark / score emotion2vec+ Large locally (B-04 scoring + B-06 benchmark).

  --raw WAV            print the untouched generate() return for the file
  --wav WAV [--pace]   slide 2 s / 1 s-hop windows over the file, score each,
                       report load time, peak RSS, p50/p95 per-window latency
  --json PATH          also write the raw per-window numbers

Real model only. Nothing here fabricates scores or timings. Run from the repo root
with the live venv: python scripts/benchmark_emotion.py --wav x.wav
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import statistics
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.adapters.emotion2vec import Emotion2vecLargeScorer  # noqa: E402
from backend.app.audio.window_scheduler import WindowScheduler  # noqa: E402
from backend.app.audio_ai_ports import PcmFrame  # noqa: E402


def read_wav16k_mono(path: str) -> bytes:
    with wave.open(path, "rb") as w:
        if w.getframerate() != 16000 or w.getsampwidth() != 2:
            raise SystemExit(f"need 16 kHz 16-bit wav, got {w.getframerate()} Hz / {w.getsampwidth()*8}-bit")
        ch = w.getnchannels()
        data = w.readframes(w.getnframes())
    if ch == 2:
        import array
        a = array.array("h"); a.frombytes(data)
        data = array.array("h", ((a[i] + a[i + 1]) // 2 for i in range(0, len(a), 2))).tobytes()
    elif ch != 1:
        raise SystemExit("mono or stereo only")
    return data


def peak_rss_mib() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**20 if platform.system() == "Darwin" else r / 1024


def pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--wav", help="16 kHz 16-bit wav to window")
    p.add_argument("--raw", help="print raw generate() value for this file")
    p.add_argument("--cache-dir", default=str(Path("~/model-cache/emotion2vec_plus_large").expanduser()))
    p.add_argument("--device", default="cpu")
    p.add_argument("--pace", action="store_true", help="feed one second of audio per second")
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--json", help="write raw numbers here")
    a = p.parse_args()
    if not (a.wav or a.raw):
        p.error("give --wav or --raw")

    sc = Emotion2vecLargeScorer(cache_dir=a.cache_dir, device=a.device)
    t0 = time.perf_counter()
    sc.load()
    load_s = time.perf_counter() - t0
    rss_after_load = peak_rss_mib()
    print(f"load: {load_s:.2f} s  source={sc.model_source}  device={a.device}  peak RSS {rss_after_load:.0f} MiB")

    if a.raw:
        print(repr(sc.score_raw(a.raw)))
    if not a.wav:
        return 0

    pcm = read_wav16k_mono(a.wav)
    sch = WindowScheduler()
    sch.begin_epoch("bench", 0, 0)
    windows, step = [], 16000  # feed 1 s frames, as a paced mic would
    t_feed0 = time.perf_counter()
    for s in range(0, len(pcm) // 2, step):
        n = min(step, len(pcm) // 2 - s)
        windows += sch.push(PcmFrame("bench", 0, s, s + n, pcm[2 * s: 2 * (s + n)]))
        if a.pace:
            time.sleep(max(0.0, (s + n) / 16000 - (time.perf_counter() - t_feed0)))
    print(f"windows emitted: {len(windows)} from {len(pcm)/32000:.1f} s audio")
    for w in windows[: a.warmup]:
        sc.score(w)  # warm-up, excluded
    rows, lat = [], []
    for w in windows[a.warmup:] if len(windows) > a.warmup else windows:
        t = time.perf_counter()
        r = sc.score(w)
        ms = (time.perf_counter() - t) * 1000
        lat.append(ms)
        top = max(r.scores, key=r.scores.get)
        rows.append({"start": w.start_sample, "ms": round(ms, 1), "top": top,
                     "scores": {k: round(v, 4) for k, v in r.scores.items()}})
        print(f"[{w.start_sample:>7},{w.end_sample:>7}) {ms:7.1f} ms  {top:<10} {r.scores[top]:.3f}")
    summary = {"windows_timed": len(lat), "warmup": a.warmup, "load_s": round(load_s, 2),
               "peak_rss_mib": round(peak_rss_mib()), "p50_ms": round(pct(lat, .5), 1),
               "p95_ms": round(pct(lat, .95), 1), "mean_ms": round(statistics.mean(lat), 1),
               "min_ms": round(min(lat), 1), "max_ms": round(max(lat), 1),
               "device": a.device, "paced": a.pace}
    print(json.dumps(summary))
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

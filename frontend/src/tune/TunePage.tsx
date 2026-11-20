// Tuning mode (?tune=1): model-only vocal-cue scores from the presenter's mic, for setting
// thresholds. It talks to the dev route WS /ws/dev/tune (live backend only), outside the v1
// protocol. There is no transcript here, and nothing on this page is sent to Scribe.
import { useCallback, useEffect, useRef, useState } from 'react';
import { MicCapture, CaptureError } from '../audio/capture';
import { backendOrigin } from '../app/config';
import { EmotionProfile } from '../visual';
import { ALL_LABELS, type ScoreMap, type VisualSettings } from '../visual/contract';
import { LABEL_TEXT } from '../visual/palette';
import './tune.css';

interface Candidate {
  primary: string;
  secondary: string | null;
  support: number;
  visual_intensity: number;
  opacity: number;
  blend_weight: number | null;
}

interface TuneWindow {
  type: 'tune.window';
  kind: 'scored' | 'silence' | 'dropped' | 'failed';
  start_ms: number;
  end_ms: number;
  latency_ms: number;
  model_ms?: number;
  scores?: ScoreMap;
  smoothed?: ScoreMap;
  top_label?: string;
  classify?: Candidate | null;
}

type Phase = 'idle' | 'connecting' | 'listening' | 'error';

const SETTINGS: VisualSettings = { showLabels: false, palette: 'default', reducedMotion: false, mismatch: false };

export function tuneUrl(origin: string): string {
  return origin.replace(/^http/, 'ws') + '/ws/dev/tune';
}

export default function TunePage() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const [modelState, setModelState] = useState<string>('unknown');
  const [thresholds, setThresholds] = useState<Record<string, number> | null>(null);
  const [latest, setLatest] = useState<TuneWindow | null>(null);
  const [log, setLog] = useState<TuneWindow[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const capRef = useRef<MicCapture | null>(null);

  const stop = useCallback(async () => {
    const cap = capRef.current;
    capRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    await cap?.close();
    setPhase((p) => (p === 'error' ? p : 'idle'));
  }, []);

  useEffect(() => () => void stop(), [stop]);

  const start = useCallback(async () => {
    setMessage(null);
    setPhase('connecting');
    const ws = new WebSocket(tuneUrl(backendOrigin()));
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      let m: { type: string; [k: string]: unknown };
      try {
        m = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (m.type === 'tune.hello') {
        setModelState(String(m.model_state));
        setThresholds(m.thresholds as Record<string, number>);
      } else if (m.type === 'tune.model') {
        setModelState(String(m.model_state));
      } else if (m.type === 'tune.warning') {
        if (m.code === 'MODEL_NOT_READY') setMessage(`Model not ready yet (${String(m.model_state)}). Frames are dropped until it is.`);
        else setMessage(`Warning: ${String(m.code)}`);
      } else if (m.type === 'tune.error') {
        setMessage(`${String(m.message)} Start the backend with scripts/demo_live.sh.`);
        setPhase('error');
      } else if (m.type === 'tune.window') {
        const w = m as unknown as TuneWindow;
        if (w.kind === 'scored') {
          setLatest(w);
          setMessage(null);
        }
        setLog((l) => [w, ...l].slice(0, 12));
      }
    };
    ws.onclose = () => {
      if (wsRef.current === ws) {
        void stop();
        setPhase((p) => (p === 'error' ? p : 'idle'));
        setMessage((cur) => cur ?? 'Disconnected. The tuning route exists only on a live backend (scripts/demo_live.sh).');
      }
    };
    const opened = await new Promise<boolean>((resolve) => {
      ws.onopen = () => resolve(true);
      ws.onerror = () => resolve(false);
    });
    if (!opened) {
      setPhase('error');
      setMessage('Could not reach the tuning route. Start the live backend: scripts/demo_live.sh (the route is off in replay mode).');
      wsRef.current = null;
      return;
    }
    const cap = new MicCapture({
      onFrame: (frame) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(frame);
      },
    });
    capRef.current = cap;
    try {
      await cap.open();
    } catch (err) {
      setPhase('error');
      setMessage(err instanceof CaptureError ? err.message : 'The microphone could not be opened.');
      ws.close();
      return;
    }
    cap.arm();
    setPhase('listening');
  }, [stop]);

  const reset = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: 'tune.reset' }));
    setLatest(null);
    setLog([]);
  }, []);

  const shown = latest?.smoothed ?? null;
  const cls = latest?.classify ?? null;

  return (
    <div className="tune et-visual">
      <header className="tune-head">
        <div>
          <h1>Tuning mode — model only, no transcript</h1>
          <p>
            Scores from emotion2vec+ Large for each 2 s window of your microphone (1 s hop). Nothing here is a caption,
            and nothing is sent to ElevenLabs. Detected vocal cues, not feelings.
          </p>
        </div>
        <div className="tune-actions">
          <span className={`tune-model tune-model--${modelState}`}>Model: {modelState}</span>
          {phase === 'listening' ? (
            <>
              <button type="button" className="btn" onClick={reset}>
                Clear
              </button>
              <button type="button" className="btn" onClick={() => void stop()}>
                Stop
              </button>
            </>
          ) : (
            <button type="button" className="btn primary" onClick={() => void start()} disabled={phase === 'connecting'}>
              {phase === 'connecting' ? 'Connecting…' : 'Start mic'}
            </button>
          )}
          <a className="btn ghost" href={window.location.pathname}>
            Back to app
          </a>
        </div>
      </header>
      {message ? (
        <p className="tune-msg" role="status">
          {message}
        </p>
      ) : null}

      <main className="tune-grid">
        <div>
          <EmotionProfile latest={shown} settings={SETTINGS} />
          <p className="tune-note">Radar and mix show the smoothed scores that the live pipeline classifies.</p>
        </div>

        <section className="et-panel tune-panel" aria-label="Current window">
          <header className="et-panel__head">
            <h2>Current window</h2>
            <span className="et-pill">{latest ? `${(latest.start_ms / 1000).toFixed(0)}–${(latest.end_ms / 1000).toFixed(0)} s` : 'Waiting'}</span>
          </header>
          <dl className="et-facts">
            <div>
              <dt>Top raw label</dt>
              <dd>{latest?.top_label ? LABEL_TEXT[latest.top_label as keyof typeof LABEL_TEXT] ?? latest.top_label : '--'}</dd>
            </div>
            <div>
              <dt>classify() result</dt>
              <dd data-testid="tune-classify">
                {latest ? (cls ? `${cls.primary}${cls.secondary ? ' + ' + cls.secondary : ''}` : 'suppressed (no cloud)') : '--'}
              </dd>
            </div>
            <div>
              <dt>Support / opacity</dt>
              <dd>{cls ? `${cls.support.toFixed(2)} / ${cls.opacity.toFixed(2)}` : '--'}</dd>
            </div>
            <div>
              <dt>Model time / latency</dt>
              <dd>{latest ? `${latest.model_ms ?? '--'} ms / ${latest.latency_ms} ms` : '--'}</dd>
            </div>
          </dl>
          <table className="et-scores tune-scores">
            <caption>Nine scores: raw window and smoothed</caption>
            <thead>
              <tr>
                <th scope="col">Label</th>
                <th scope="col">Raw</th>
                <th scope="col">Smoothed</th>
              </tr>
            </thead>
            <tbody>
              {ALL_LABELS.map((l) => (
                <tr key={l} className={latest?.top_label === l ? 'is-primary' : undefined}>
                  <th scope="row">{LABEL_TEXT[l]}</th>
                  <td>{latest?.scores ? latest.scores[l].toFixed(3) : '--'}</td>
                  <td>{latest?.smoothed ? latest.smoothed[l].toFixed(3) : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="et-panel tune-panel" aria-label="Thresholds and recent windows">
          <header className="et-panel__head">
            <h2>Current thresholds</h2>
          </header>
          {thresholds ? (
            <dl className="tune-thresholds">
              {Object.entries(thresholds).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="tune-note">Shown once connected. Change them in backend/.env (EMOTION_*) and restart.</p>
          )}
          <h3 className="tune-sub">Recent windows</h3>
          <ol className="tune-log">
            {log.map((w) => (
              <li key={`${w.start_ms}-${w.kind}`}>
                <span>{(w.start_ms / 1000).toFixed(0)} s</span>
                <span>{w.kind}</span>
                <span>{w.kind === 'scored' ? (w.classify ? w.classify.primary : 'suppressed') : ''}</span>
                <span>{w.top_label ?? ''}</span>
              </li>
            ))}
          </ol>
        </section>
      </main>
    </div>
  );
}

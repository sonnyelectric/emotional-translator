// Resilience UI (C-05): reason-specific banners for warnings and errors. Committed text is
// never cleared by any of these; only Reset clears it.
import type { SessionStatusPayload } from '../protocol/events';
import type { Notice } from '../state/reducer';
import type { LocalIssue } from '../app/liveSession';
import type { ReplayError } from '../protocol/replayClient';

const FATAL_HINTS: Record<string, string> = {
  LIVE_NOT_CONFIGURED: 'Live transcription is not configured on this laptop. Replay still works.',
  SCRIBE_AUTH: 'The transcription service rejected the API key. Check backend/.env, or use Replay.',
  SCRIBE_QUOTA: 'The transcription quota is used up. Use Replay, or add credits.',
  SCRIBE_TERMS: 'The transcription account needs its terms accepted. Use Replay meanwhile.',
  SCRIBE_RETRY_EXHAUSTED: 'Transcription could not reconnect. Your transcript is kept. Reset, then Start again.',
};

const WARNING_TITLES: Record<string, string> = {
  SCRIBE_RECONNECTING: 'Transcription reconnecting',
  EMOTION_MODEL_UNAVAILABLE: 'Emotion cues unavailable',
  EMOTION_INFERENCE_SLOW: 'Emotion cues delayed',
  ALIGNMENT_TIMESTAMPS_MISSING: 'Word timing missing',
  ALIGNMENT_TIMESTAMP_MISMATCH: 'Word timing mismatch',
};

interface Props {
  mode: 'live' | 'replay';
  notices: readonly Notice[];
  error: { code: string; message: string } | null;
  localIssue: LocalIssue | null;
  status: SessionStatusPayload | null;
  replayError: ReplayError | null;
  canUseBundled: boolean;
  onUseBundled(): void;
  onSwitchToReplay?: () => void;
}

export function Notices(p: Props) {
  // Latest notice per code, newest first, max 3 session warnings and 2 alignment warnings.
  const latest = new Map<string, Notice>();
  for (const n of p.notices) latest.set(`${n.kind}:${n.code}`, n);
  const items = [...latest.values()].sort((a, b) => b.seq - a.seq);
  const session = items.filter((n) => n.kind === 'session.warning').slice(0, 3);
  const alignment = items.filter((n) => n.kind === 'alignment.warning').slice(0, 2);
  const saved = p.mode === 'replay' ? 'Saved warning: ' : '';
  const degraded =
    p.mode === 'live' && p.status?.mode === 'live' && (p.status.emotion_model === 'degraded' || p.status.emotion_model === 'failed');
  const reconnecting = p.mode === 'live' && p.status?.mode === 'live' && p.status.scribe === 'reconnecting';

  const anything = p.error || p.localIssue || p.replayError || session.length || alignment.length || degraded || reconnecting;
  if (!anything) return <div className="notices" aria-live="polite" />;

  return (
    <div className="notices" aria-live="polite" data-testid="notices">
      {p.error && (
        <div className="notice error" role="alert" data-code={p.error.code}>
          <strong>{p.mode === 'replay' ? 'Saved error' : 'Live session ended'}</strong>
          <span>{FATAL_HINTS[p.error.code] ?? p.error.message}</span>
          {p.onSwitchToReplay && (
            <button type="button" className="btn small" onClick={p.onSwitchToReplay}>
              Switch to Replay
            </button>
          )}
        </div>
      )}
      {p.localIssue && (
        <div className={`notice ${p.localIssue.severity}`} role={p.localIssue.severity === 'error' ? 'alert' : undefined} data-code={p.localIssue.code}>
          <strong>
            {p.localIssue.code === 'MIC_DENIED'
              ? 'Microphone blocked'
              : p.localIssue.code === 'AUDIO_CONGESTED'
                ? 'Paused to protect audio'
                : p.localIssue.code === 'BACKEND_UNREACHABLE'
                  ? 'Backend not reachable'
                  : p.localIssue.code === 'DISCONNECTED'
                    ? 'Disconnected'
                    : 'Microphone problem'}
          </strong>
          <span>{p.localIssue.message}</span>
          {p.onSwitchToReplay && p.localIssue.severity === 'error' && (
            <button type="button" className="btn small" onClick={p.onSwitchToReplay}>
              Switch to Replay
            </button>
          )}
        </div>
      )}
      {p.replayError && (
        <div className="notice error" role="alert" data-code={p.replayError.code} data-testid="replay-error">
          <strong>Replay unavailable</strong>
          <span>{p.replayError.message}</span>
          {p.canUseBundled && (
            <button type="button" className="btn small" onClick={p.onUseBundled}>
              Use the copy bundled in this page
            </button>
          )}
        </div>
      )}
      {reconnecting && !session.some((n) => n.code === 'SCRIBE_RECONNECTING') && (
        <div className="notice warning">
          <strong>Transcription reconnecting</strong>
          <span>Committed words are kept. New text resumes when the connection returns.</span>
        </div>
      )}
      {degraded && !session.some((n) => n.code.startsWith('EMOTION_')) && (
        <div className="notice warning">
          <strong>Text only</strong>
          <span>Emotion cues are degraded. Transcription continues.</span>
        </div>
      )}
      {session.map((n) => (
        <div key={`${n.code}-${n.seq}`} className="notice warning" data-code={n.code}>
          <strong>
            {saved}
            {WARNING_TITLES[n.code] ?? 'Notice'}
          </strong>
          <span>{n.message}</span>
        </div>
      ))}
      {alignment.map((n) => (
        <div key={`${n.code}-${n.seq}`} className="notice quiet" data-code={n.code}>
          <strong>
            {saved}
            {WARNING_TITLES[n.code] ?? 'Alignment'}
          </strong>
          <span>{n.message} This sentence stays plain text.</span>
        </div>
      ))}
    </div>
  );
}

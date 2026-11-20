import type { SessionStatusPayload } from '../protocol/events';
import type { LivePhase, LocalIssue } from '../app/liveSession';
import type { ReplayPhase } from '../replay/clock';

export interface StatusInfo {
  label: string;
  tone: 'idle' | 'ok' | 'busy' | 'warn' | 'error';
  detail?: string;
}

export function describeStatus(args: {
  mode: 'live' | 'replay';
  livePhase: LivePhase;
  status: SessionStatusPayload | null;
  replayPhase: ReplayPhase | 'replay_loading';
  error: { code: string; message: string } | null;
  localIssue: LocalIssue | null;
}): StatusInfo {
  const { mode, livePhase, status, replayPhase, error, localIssue } = args;
  if (mode === 'replay') {
    switch (replayPhase) {
      case 'replay_loading':
        return { label: 'Loading saved result', tone: 'busy' };
      case 'replay_playing':
        return { label: 'Playing saved result', tone: 'ok' };
      case 'replay_paused':
        return { label: 'Replay paused', tone: 'idle' };
      case 'replay_done':
        return { label: 'Replay finished', tone: 'idle' };
      default:
        return { label: 'Replay ready', tone: 'idle' };
    }
  }
  if (error) return { label: 'Error', tone: 'error', detail: error.code };
  if (localIssue?.severity === 'error') return { label: localIssue.code === 'MIC_DENIED' ? 'Mic blocked' : 'Disconnected', tone: 'error' };
  if (livePhase === 'permission') return { label: 'Waiting for mic permission', tone: 'busy' };
  if (livePhase === 'connecting' && (!status || status.mode !== 'live')) return { label: 'Connecting', tone: 'busy' };
  if (!status || status.mode !== 'live') return { label: livePhase === 'closed' ? 'Disconnected' : 'Ready', tone: 'idle' };
  const degraded = status.emotion_model === 'degraded' || status.emotion_model === 'failed';
  const reconnecting = status.scribe === 'reconnecting';
  switch (status.state) {
    case 'listening':
      if (reconnecting) return { label: 'Transcription reconnecting', tone: 'warn' };
      if (degraded) return { label: 'Listening · text only', tone: 'warn', detail: 'Emotion model degraded' };
      if (status.emotion_model === 'loading') return { label: 'Listening · model loading', tone: 'warn' };
      return { label: 'Listening', tone: 'ok' };
    case 'connecting':
      return { label: reconnecting ? 'Reconnecting' : 'Connecting', tone: 'busy' };
    case 'paused':
      return { label: 'Paused', tone: 'idle' };
    case 'stopping':
      return { label: 'Stopping', tone: 'busy' };
    case 'stopped':
      return { label: 'Stopped', tone: 'idle' };
    case 'error':
      return { label: 'Error', tone: 'error' };
    default:
      return { label: 'Ready', tone: 'idle' };
  }
}

export function StatusPill({ info }: { info: StatusInfo }) {
  return (
    <span className={`status-pill tone-${info.tone}`} role="status" data-testid="status-pill" title={info.detail}>
      <span className="dot" aria-hidden="true" />
      {info.label}
    </span>
  );
}

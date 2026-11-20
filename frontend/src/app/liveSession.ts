// Live session controller: mic capture + WebSocket + command sequencing.
// Loaded with a dynamic import so the static replay build never includes mic/WS code.
import { MicCapture, CaptureError, type CaptureErrorKind } from '../audio/capture';
import { LiveClient } from '../protocol/liveClient';
import type { InboundEvent, SessionStatusPayload } from '../protocol/events';

export type LivePhase =
  | 'idle' // nothing open
  | 'permission' // waiting for the mic prompt
  | 'connecting' // socket opening / start sent
  | 'active' // transport open, server drives state
  | 'closed'; // transport ended; content kept until reset

export interface LiveCallbacks {
  onEvent(e: InboundEvent): void;
  onPhase(p: LivePhase): void;
  /** Frontend-only problems (permission, disconnect, congestion). */
  onLocalIssue(issue: LocalIssue | null): void;
  onDiagnostic(msg: string): void;
}

export interface LocalIssue {
  code: 'MIC_DENIED' | 'MIC_UNAVAILABLE' | 'MIC_FAILED' | 'DISCONNECTED' | 'BACKEND_UNREACHABLE' | 'AUDIO_CONGESTED';
  message: string;
  severity: 'warning' | 'error';
}

function issueForCapture(kind: CaptureErrorKind): LocalIssue {
  switch (kind) {
    case 'denied':
      return {
        code: 'MIC_DENIED',
        message: 'Microphone access was blocked. Allow it from the address bar (site settings), then press Start again.',
        severity: 'error',
      };
    case 'no-device':
      return { code: 'MIC_UNAVAILABLE', message: 'No microphone was found. Connect one and press Start again.', severity: 'error' };
    case 'unsupported':
      return { code: 'MIC_FAILED', message: 'This browser cannot capture microphone audio here. Use Chrome on localhost.', severity: 'error' };
    default:
      return { code: 'MIC_FAILED', message: 'The microphone could not be started. Press Start to try again.', severity: 'error' };
  }
}

export class LiveSession {
  private capture: MicCapture | null = null;
  private client: LiveClient;
  private phase: LivePhase = 'idle';
  private sawTerminal = false;
  /** Incremented on each start/teardown so stale async steps abort. */
  private attempt = 0;

  constructor(
    origin: string,
    private readonly cb: LiveCallbacks,
    private readonly diagnostics = false,
  ) {
    this.client = new LiveClient(origin, {
      onOpen: () => {
        this.everOpened = true;
        this.client.send('session.start');
      },
      onEvent: (e) => {
        if (e.type === 'session.status' && !('__unknown' in e)) {
          const s = e.payload as SessionStatusPayload;
          if (s.state === 'stopped' || s.state === 'error') this.sawTerminal = true;
        }
        if (e.type === 'session.error') this.sawTerminal = true;
        this.cb.onEvent(e);
      },
      onClose: (info) => {
        void this.releaseCapture();
        const wasActive = this.phase === 'active' || this.phase === 'connecting';
        this.setPhase('closed');
        if (wasActive && !this.sawTerminal) {
          this.cb.onLocalIssue({
            code: info.code === 1006 && !this.everOpened ? 'BACKEND_UNREACHABLE' : 'DISCONNECTED',
            message:
              info.code === 1006 && !this.everOpened
                ? 'Could not reach the local backend. Check that it is running, or switch to Replay.'
                : 'Connection to the local backend closed. Your transcript is kept; press Reset to start again.',
            severity: 'error',
          });
        }
      },
      onDiagnostic: (m) => this.cb.onDiagnostic(m),
    });
  }

  private everOpened = false;

  get currentPhase(): LivePhase {
    return this.phase;
  }

  get transportOpen(): boolean {
    return this.client.isOpen;
  }

  private setPhase(p: LivePhase) {
    this.phase = p;
    this.cb.onPhase(p);
  }

  /** Start in Live: permission first, then socket, then `session.start`. */
  async start(): Promise<void> {
    if (this.phase !== 'idle' && this.phase !== 'closed') return;
    const attempt = ++this.attempt;
    this.sawTerminal = false;
    this.everOpened = false;
    this.cb.onLocalIssue(null);
    this.setPhase('permission');
    const capture = new MicCapture({
      onFrame: (frame) => this.forward(frame),
      diagnostics: this.diagnostics,
    });
    this.capture = capture;
    try {
      await capture.open();
    } catch (err) {
      if (attempt !== this.attempt) return;
      this.capture = null;
      await capture.close();
      this.setPhase('idle');
      this.cb.onLocalIssue(issueForCapture(err instanceof CaptureError ? err.kind : 'failed'));
      return;
    }
    if (attempt !== this.attempt) {
      await capture.close();
      return;
    }
    if (this.diagnostics) {
      // Settings only (rates and processing flags), never audio content.
      console.info('[capture] context rate', capture.diag.contextRate, 'track settings', capture.diag.trackSettings);
    }
    this.setPhase('connecting');
    this.client.connect();
  }

  /** Called whenever the reducer's accepted live status changes. Arms capture only on a valid listening ack. */
  syncStatus(status: SessionStatusPayload | null): void {
    if (!status || status.mode !== 'live') return;
    if (this.phase === 'connecting') {
      this.setPhase('active');
    }
    const formatOk = status.sample_rate_hz === 16000 && status.channels === 1 && status.sample_format === 's16le';
    if (status.state === 'listening' && formatOk) {
      if (this.capture && !this.capture.isArmed) this.capture.arm();
    } else if (status.state === 'stopped' || status.state === 'error') {
      void this.releaseCapture();
    } else if (status.state !== 'listening') {
      this.capture?.disarm();
    }
  }

  private forward(frame: ArrayBuffer) {
    const r = this.client.sendAudio(frame);
    if (r === 'congested') {
      this.capture?.disarm();
      this.client.send('session.pause');
      void this.capture?.suspend();
      this.cb.onLocalIssue({
        code: 'AUDIO_CONGESTED',
        message: 'Audio could not be sent fast enough, so listening was paused rather than skipping speech. Press Resume.',
        severity: 'warning',
      });
    } else if (r === 'closed') {
      this.capture?.disarm();
    }
  }

  async pause(): Promise<void> {
    if (!this.capture) return;
    await this.capture.drainAndDisarm();
    this.client.send('session.pause');
    await this.capture.suspend();
  }

  async resume(): Promise<void> {
    if (!this.capture) return;
    this.cb.onLocalIssue(null);
    await this.capture.resume();
    // Re-armed by syncStatus on the next `listening` ack (new upstream epoch).
    this.client.send('session.resume');
  }

  async stop(): Promise<void> {
    if (this.phase === 'permission') {
      // Cancel a pending permission flow.
      this.attempt++;
      await this.releaseCapture();
      this.setPhase('idle');
      return;
    }
    if (this.capture) await this.capture.drainAndDisarm();
    const sent = this.client.send('session.stop');
    await this.releaseCapture();
    if (!sent) {
      this.client.close();
      this.setPhase('closed');
    }
  }

  /** Reset over the open transport if possible. Returns true if the server will acknowledge. */
  reset(): boolean {
    if (this.client.isOpen) {
      return this.client.send('session.reset');
    }
    this.attempt++;
    void this.releaseCapture();
    this.client.close();
    this.setPhase('idle');
    this.cb.onLocalIssue(null);
    return false;
  }

  /** Forget the transport entirely (after local reset, mode switch, unmount). */
  async dispose(): Promise<void> {
    this.attempt++;
    this.client.close();
    await this.releaseCapture();
    this.phase = 'idle';
  }

  /** After a reset ack over an open socket, the next Start reuses the transport. */
  startOnOpenTransport(): void {
    if (!this.client.isOpen) return;
    void this.startReusingTransport();
  }

  private async startReusingTransport() {
    const attempt = ++this.attempt;
    this.sawTerminal = false;
    this.cb.onLocalIssue(null);
    this.setPhase('permission');
    const capture = new MicCapture({ onFrame: (f) => this.forward(f), diagnostics: this.diagnostics });
    this.capture = capture;
    try {
      await capture.open();
    } catch (err) {
      if (attempt !== this.attempt) return;
      this.capture = null;
      this.setPhase('active');
      this.cb.onLocalIssue(issueForCapture(err instanceof CaptureError ? err.kind : 'failed'));
      return;
    }
    if (attempt !== this.attempt) {
      await capture.close();
      return;
    }
    this.setPhase('active');
    this.client.send('session.start');
  }

  private async releaseCapture() {
    const c = this.capture;
    this.capture = null;
    if (c) await c.close();
  }
}

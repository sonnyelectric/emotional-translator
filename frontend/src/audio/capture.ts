// Microphone capture: getUserMedia (processing off, PLAN D8) -> default-rate AudioContext ->
// AudioWorklet (downmix, resample to 16 kHz, s16le, 40 ms frames) -> onFrame callback.
// Frames are only forwarded while `armed`; the live client arms on the `listening` ack.
import workletUrl from './capture.worklet.ts?worker&url';

export type CaptureErrorKind = 'denied' | 'no-device' | 'unsupported' | 'failed';

export class CaptureError extends Error {
  constructor(
    readonly kind: CaptureErrorKind,
    message: string,
  ) {
    super(message);
  }
}

export interface CaptureDiagnostics {
  contextRate: number;
  trackSettings: MediaTrackSettings | null;
  framesSent: number;
  framesDropped: number;
  lastFrameAt: number;
}

export interface CaptureOptions {
  onFrame: (frame: ArrayBuffer) => void;
  /** Opt-in latency diagnostics (performance.now() per frame). No audio content is logged. */
  diagnostics?: boolean;
}

export const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    channelCount: 1,
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
  },
  video: false,
};

export class MicCapture {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private sink: GainNode | null = null;
  private armed = false;
  private closed = false;
  private flushResolve: (() => void) | null = null;
  readonly diag: CaptureDiagnostics = {
    contextRate: 0,
    trackSettings: null,
    framesSent: 0,
    framesDropped: 0,
    lastFrameAt: 0,
  };

  constructor(private readonly opts: CaptureOptions) {}

  /** Request permission and build the audio graph. Does not forward audio until `arm()`. */
  async open(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) throw new CaptureError('unsupported', 'This browser cannot capture audio.');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
    } catch (err) {
      const name = (err as DOMException).name;
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        throw new CaptureError('denied', 'Microphone permission was denied.');
      }
      if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        throw new CaptureError('no-device', 'No usable microphone was found.');
      }
      throw new CaptureError('failed', 'The microphone could not be opened.');
    }
    if (this.closed) {
      this.releaseTracks();
      throw new CaptureError('failed', 'Capture was cancelled.');
    }
    try {
      const track = this.stream.getAudioTracks()[0];
      this.diag.trackSettings = track?.getSettings?.() ?? null;
      this.ctx = new AudioContext(); // device default rate; the worklet resamples
      this.diag.contextRate = this.ctx.sampleRate;
      await this.ctx.audioWorklet.addModule(workletUrl);
      if (this.closed) throw new Error('cancelled');
      this.source = this.ctx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.ctx, 'pcm-capture', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCountMode: 'explicit',
        channelCount: Math.max(1, Math.min(2, this.source.channelCount || 1)),
      });
      this.node.port.onmessage = this.onMessage;
      // A muted path to the destination keeps the node pulled in all browsers.
      this.sink = this.ctx.createGain();
      this.sink.gain.value = 0;
      this.source.connect(this.node);
      this.node.connect(this.sink);
      this.sink.connect(this.ctx.destination);
      if (this.ctx.state === 'suspended') await this.ctx.resume();
    } catch (err) {
      await this.close();
      if (err instanceof CaptureError) throw err;
      throw new CaptureError('failed', 'Audio processing could not start.');
    }
  }

  private onMessage = (ev: MessageEvent) => {
    const msg = ev.data as { type: string; frame?: ArrayBuffer };
    if (msg.type === 'frame' && msg.frame) {
      if (!this.armed || this.closed) {
        this.diag.framesDropped++;
        return;
      }
      this.diag.framesSent++;
      if (this.opts.diagnostics) this.diag.lastFrameAt = performance.now();
      this.opts.onFrame(msg.frame);
    } else if (msg.type === 'flushed') {
      this.flushResolve?.();
      this.flushResolve = null;
    }
  };

  /** Start forwarding frames (after a valid live `listening` ack). Resets resampler phase for a new epoch. */
  arm(): void {
    if (this.closed || !this.node) return;
    this.node.port.postMessage({ type: 'reset' });
    this.armed = true;
  }

  get isArmed(): boolean {
    return this.armed;
  }

  /**
   * Stop forwarding after sending the complete queued audio: the worklet emits its
   * >= 20 ms remainder, then we disarm. Resolves before the caller sends Pause/Stop.
   */
  async drainAndDisarm(timeoutMs = 250): Promise<void> {
    if (!this.node || !this.armed) {
      this.armed = false;
      return;
    }
    await new Promise<void>((resolve) => {
      const t = setTimeout(resolve, timeoutMs);
      this.flushResolve = () => {
        clearTimeout(t);
        resolve();
      };
      this.node!.port.postMessage({ type: 'flush' });
    });
    this.armed = false;
  }

  disarm(): void {
    this.armed = false;
  }

  async suspend(): Promise<void> {
    if (this.ctx && this.ctx.state === 'running') await this.ctx.suspend();
  }

  async resume(): Promise<void> {
    if (this.ctx && this.ctx.state === 'suspended') await this.ctx.resume();
  }

  private releaseTracks() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  /** Release the mic, worklet and context. Safe to call repeatedly. */
  async close(): Promise<void> {
    this.closed = true;
    this.armed = false;
    this.flushResolve?.();
    this.flushResolve = null;
    try {
      this.source?.disconnect();
      this.node?.disconnect();
      this.sink?.disconnect();
      if (this.node) this.node.port.onmessage = null;
    } catch {
      /* already disconnected */
    }
    this.releaseTracks();
    const ctx = this.ctx;
    this.ctx = null;
    this.node = null;
    this.source = null;
    this.sink = null;
    if (ctx && ctx.state !== 'closed') {
      try {
        await ctx.close();
      } catch {
        /* ignore */
      }
    }
  }
}

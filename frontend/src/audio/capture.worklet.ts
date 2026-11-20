// AudioWorklet processor: converts the context's Float32 input to 16 kHz mono s16le
// 40 ms frames and posts them (transferred) to the main thread.
// Loaded via `?worker&url` so Vite bundles it with its pcm.ts import.
import { PcmEncoder } from './pcm';

declare const sampleRate: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
  constructor();
}
declare function registerProcessor(name: string, ctor: new () => AudioWorkletProcessor): void;

type InMsg = { type: 'flush' } | { type: 'reset' };

class PcmCaptureProcessor extends AudioWorkletProcessor {
  private encoder = new PcmEncoder(sampleRate);
  private frames = 0;

  constructor() {
    super();
    this.port.onmessage = (ev: MessageEvent<InMsg>) => {
      if (ev.data.type === 'flush') {
        const tail = this.encoder.flush(this.emit);
        this.port.postMessage({ type: 'flushed', tailSamples: tail });
      } else if (ev.data.type === 'reset') {
        this.encoder = new PcmEncoder(sampleRate);
      }
    };
    this.port.postMessage({ type: 'ready', inputRate: sampleRate });
  }

  private emit = (frame: ArrayBuffer) => {
    this.frames++;
    this.port.postMessage({ type: 'frame', frame, index: this.frames }, [frame]);
  };

  process(inputs: Float32Array[][]): boolean {
    const input = inputs[0];
    if (input && input.length > 0) this.encoder.push(input, this.emit);
    return true;
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor);

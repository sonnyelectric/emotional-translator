// Pure PCM conversion used by the AudioWorklet and by unit tests.
// Pipeline: downmix (average channels) -> band-limited resample to 16 kHz -> clamp ->
// signed 16-bit little-endian -> fixed 640-sample (40 ms, 1,280-byte) frames.
// The resampler keeps its phase and filter history across calls, so splitting input
// into arbitrary block sizes gives byte-identical output.

export const TARGET_RATE = 16000;
export const FRAME_SAMPLES = 640; // 40 ms at 16 kHz
export const MIN_TAIL_SAMPLES = 320; // 20 ms: shorter tails are dropped on flush

/** Average all channels into `out` (length = channel length). */
export function downmix(channels: readonly Float32Array[], out?: Float32Array): Float32Array {
  const n = channels.length > 0 ? channels[0].length : 0;
  const dst = out && out.length >= n ? out.subarray(0, n) : new Float32Array(n);
  if (channels.length === 0) return dst;
  if (channels.length === 1) {
    dst.set(channels[0].subarray(0, n));
    return dst;
  }
  const k = 1 / channels.length;
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (let c = 0; c < channels.length; c++) s += channels[c][i];
    dst[i] = s * k;
  }
  return dst;
}

/** Clamp to [-1, 1] and map to the full Int16 range (-32768..32767). */
export function floatToInt16(x: number): number {
  if (!(x === x)) return 0; // NaN
  if (x >= 1) return 32767;
  if (x <= -1) return -32768;
  return x < 0 ? Math.round(x * 32768) : Math.round(x * 32767);
}

/** Windowed-sinc (Blackman) low-pass taps, normalized to unity DC gain. */
export function lowpassTaps(cutoffHz: number, sampleRate: number, halfWidth: number): Float32Array {
  const n = 2 * halfWidth + 1;
  const taps = new Float32Array(n);
  const fc = cutoffHz / sampleRate; // cycles per sample
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const m = i - halfWidth;
    const sinc = m === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * m) / (Math.PI * m);
    const w = 0.42 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1)) + 0.08 * Math.cos((4 * Math.PI * i) / (n - 1));
    taps[i] = sinc * w;
    sum += taps[i];
  }
  for (let i = 0; i < n; i++) taps[i] /= sum;
  return taps;
}

/**
 * Streaming resampler: FIR low-pass at the input rate (cutoff 7 kHz, below the 8 kHz
 * output Nyquist), evaluated only at the two input samples around each output position,
 * then linear interpolation. Phase is carried across calls.
 */
export class Resampler {
  readonly ratio: number; // input samples per output sample
  private readonly taps: Float32Array | null;
  private readonly half: number;
  /** Buffered mono input; buf[0] corresponds to absolute input index `base`. */
  private buf: Float32Array;
  private len = 0;
  private base: number;
  /** Absolute (fractional) input position of the next output sample. */
  private pos = 0;

  constructor(
    readonly inputRate: number,
    readonly outputRate: number = TARGET_RATE,
  ) {
    if (!(inputRate > 0) || !(outputRate > 0)) throw new Error('invalid sample rate');
    this.ratio = inputRate / outputRate;
    if (inputRate === outputRate) {
      this.taps = null;
      this.half = 0;
    } else {
      this.half = Math.max(16, Math.ceil(16 * this.ratio));
      this.taps = lowpassTaps(Math.min(7000, outputRate * 0.4375), inputRate, this.half);
    }
    // Pre-roll `half` zeros so the first outputs have filter history.
    this.buf = new Float32Array(4096);
    this.base = -this.half;
    this.len = this.half;
  }

  /** Push mono input; returns resampled output for whatever is now computable. */
  process(input: Float32Array): Float32Array {
    if (!this.taps) {
      return input.slice();
    }
    this.append(input);
    const taps = this.taps;
    const half = this.half;
    const out: number[] = [];
    const lastAbs = this.base + this.len - 1; // newest available absolute index
    for (;;) {
      const i0 = Math.floor(this.pos);
      if (i0 + 1 + half > lastAbs) break;
      const frac = this.pos - i0;
      const a = this.filtered(i0, taps, half);
      const b = frac === 0 ? 0 : this.filtered(i0 + 1, taps, half);
      out.push(a + (b - a) * frac);
      this.pos += this.ratio;
    }
    // Discard input no longer needed (keep `half` samples before the next position).
    const keepFrom = Math.floor(this.pos) - half;
    const drop = keepFrom - this.base;
    if (drop > 0) {
      this.buf.copyWithin(0, drop, this.len);
      this.len -= drop;
      this.base += drop;
    }
    return Float32Array.from(out);
  }

  private filtered(center: number, taps: Float32Array, half: number): number {
    let acc = 0;
    let j = center - half - this.base;
    const buf = this.buf;
    for (let k = 0; k < taps.length; k++, j++) acc += taps[k] * buf[j];
    return acc;
  }

  private append(input: Float32Array) {
    if (this.len + input.length > this.buf.length) {
      const next = new Float32Array(Math.max(this.buf.length * 2, this.len + input.length));
      next.set(this.buf.subarray(0, this.len));
      this.buf = next;
    }
    this.buf.set(input, this.len);
    this.len += input.length;
  }
}

/** Accumulates 16 kHz float samples into fixed-size s16le frames. */
export class FrameChunker {
  private pending: Int16Array;
  private fill = 0;

  constructor(readonly frameSamples = FRAME_SAMPLES) {
    this.pending = new Int16Array(frameSamples);
  }

  push(samples: Float32Array, emit: (frame: ArrayBuffer) => void): void {
    for (let i = 0; i < samples.length; i++) {
      this.pending[this.fill++] = floatToInt16(samples[i]);
      if (this.fill === this.frameSamples) {
        emit(encodeS16le(this.pending, this.frameSamples));
        this.fill = 0;
      }
    }
  }

  /** Emit the remainder if it is at least 20 ms; shorter tails are dropped. */
  flush(emit: (frame: ArrayBuffer) => void): number {
    const n = this.fill;
    this.fill = 0;
    if (n >= MIN_TAIL_SAMPLES) {
      emit(encodeS16le(this.pending, n));
      return n;
    }
    return 0;
  }

  get buffered(): number {
    return this.fill;
  }
}

/** Explicit little-endian encoding (independent of platform endianness). */
export function encodeS16le(samples: Int16Array, count = samples.length): ArrayBuffer {
  const buf = new ArrayBuffer(count * 2);
  const view = new DataView(buf);
  for (let i = 0; i < count; i++) view.setInt16(i * 2, samples[i], true);
  return buf;
}

/** Full capture conversion: channels at `inputRate` -> 16 kHz s16le frames. */
export class PcmEncoder {
  private readonly resampler: Resampler;
  private readonly chunker: FrameChunker;
  private mono = new Float32Array(128);

  constructor(inputRate: number, frameSamples = FRAME_SAMPLES) {
    this.resampler = new Resampler(inputRate, TARGET_RATE);
    this.chunker = new FrameChunker(frameSamples);
  }

  push(channels: readonly Float32Array[], emit: (frame: ArrayBuffer) => void): void {
    if (channels.length === 0 || channels[0].length === 0) return;
    if (this.mono.length < channels[0].length) this.mono = new Float32Array(channels[0].length);
    const mono = downmix(channels, this.mono);
    this.chunker.push(this.resampler.process(mono), emit);
  }

  flush(emit: (frame: ArrayBuffer) => void): number {
    return this.chunker.flush(emit);
  }
}

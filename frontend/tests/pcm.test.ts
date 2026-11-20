import { describe, expect, it } from 'vitest';
import {
  FRAME_SAMPLES,
  FrameChunker,
  PcmEncoder,
  Resampler,
  downmix,
  encodeS16le,
  floatToInt16,
} from '../src/audio/pcm';

function sine(freq: number, rate: number, seconds: number, amp = 0.5): Float32Array {
  const n = Math.round(rate * seconds);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = amp * Math.sin((2 * Math.PI * freq * i) / rate);
  return out;
}

function encodeAll(input: Float32Array, rate: number, block: number, channels = 1): ArrayBuffer[] {
  const enc = new PcmEncoder(rate);
  const frames: ArrayBuffer[] = [];
  for (let i = 0; i < input.length; i += block) {
    const part = input.subarray(i, Math.min(input.length, i + block));
    const ch = Array.from({ length: channels }, () => part);
    enc.push(ch, (f) => frames.push(f));
  }
  return frames;
}

function samplesOf(frames: ArrayBuffer[]): Int16Array {
  const total = frames.reduce((n, f) => n + f.byteLength / 2, 0);
  const out = new Int16Array(total);
  let o = 0;
  for (const f of frames) {
    const v = new DataView(f);
    for (let i = 0; i < f.byteLength / 2; i++) out[o++] = v.getInt16(i * 2, true);
  }
  return out;
}

/** Estimate frequency via zero crossings over the steady-state middle. */
function zeroCrossFreq(x: Int16Array, rate: number): number {
  const a = Math.floor(x.length * 0.1);
  const b = Math.floor(x.length * 0.9);
  let crossings = 0;
  for (let i = a + 1; i < b; i++) if ((x[i - 1] < 0 && x[i] >= 0) || (x[i - 1] >= 0 && x[i] < 0)) crossings++;
  return crossings / 2 / ((b - a) / rate);
}

function rms(x: Int16Array): number {
  const a = Math.floor(x.length * 0.1);
  const b = Math.floor(x.length * 0.9);
  let s = 0;
  for (let i = a; i < b; i++) s += (x[i] / 32768) ** 2;
  return Math.sqrt(s / (b - a));
}

describe('quantization', () => {
  it('clamps and uses the full signed range', () => {
    expect(floatToInt16(2)).toBe(32767);
    expect(floatToInt16(1)).toBe(32767);
    expect(floatToInt16(-1)).toBe(-32768);
    expect(floatToInt16(-5)).toBe(-32768);
    expect(floatToInt16(0)).toBe(0);
    expect(floatToInt16(NaN)).toBe(0);
    expect(floatToInt16(0.5)).toBe(16384);
  });

  it('writes little-endian bytes', () => {
    const b = new Uint8Array(encodeS16le(Int16Array.from([0x1234, -2])));
    expect(Array.from(b)).toEqual([0x34, 0x12, 0xfe, 0xff]);
  });
});

describe('downmix', () => {
  it('averages channels', () => {
    const l = Float32Array.from([1, 0.5, -1]);
    const r = Float32Array.from([-1, 0.5, 0]);
    expect(Array.from(downmix([l, r]))).toEqual([0, 0.5, -0.5]);
    expect(Array.from(downmix([l]))).toEqual([1, 0.5, -1]);
  });

  it('identical stereo channels encode the same as mono', () => {
    const x = sine(440, 48000, 0.5);
    const mono = samplesOf(encodeAll(x, 48000, 128, 1));
    const stereo = samplesOf(encodeAll(x, 48000, 128, 2));
    expect(stereo).toEqual(mono);
  });
});

describe.each([48000, 44100, 16000])('resampling from %i Hz', (rate) => {
  it('emits only exact 640-sample (1,280-byte) frames', () => {
    const frames = encodeAll(sine(300, rate, 1.3), rate, 128);
    expect(frames.length).toBeGreaterThan(0);
    for (const f of frames) expect(f.byteLength).toBe(FRAME_SAMPLES * 2);
  });

  it('preserves frequency and level of a 1 kHz tone', () => {
    const out = samplesOf(encodeAll(sine(1000, rate, 2), rate, 128));
    expect(zeroCrossFreq(out, 16000)).toBeGreaterThan(990);
    expect(zeroCrossFreq(out, 16000)).toBeLessThan(1010);
    expect(rms(out)).toBeGreaterThan(0.5 / Math.SQRT2 - 0.02);
    expect(rms(out)).toBeLessThan(0.5 / Math.SQRT2 + 0.02);
  });

  it('is continuous: block size does not change output (phase carried across buffers)', () => {
    const x = sine(523.25, rate, 1);
    const a = samplesOf(encodeAll(x, rate, 128));
    const b = samplesOf(encodeAll(x, rate, 1000));
    const c = samplesOf(encodeAll(x, rate, 37));
    expect(b).toEqual(a);
    expect(c).toEqual(a);
  });

  it('long-run sample count matches 16 kHz within one frame plus filter latency', () => {
    const seconds = 60;
    const r = new Resampler(rate);
    let produced = 0;
    const block = new Float32Array(128);
    const blocks = Math.floor((rate * seconds) / 128);
    for (let i = 0; i < blocks; i++) produced += r.process(block).length;
    const expected = (blocks * 128 * 16000) / rate;
    expect(Math.abs(produced - expected)).toBeLessThan(40);
  });
});

describe('anti-aliasing', () => {
  it('attenuates a 12 kHz tone at 48 kHz input (would alias to 4 kHz)', () => {
    const out = samplesOf(encodeAll(sine(12000, 48000, 1), 48000, 128));
    expect(rms(out)).toBeLessThan(0.01);
  });

  it('attenuates a 10 kHz tone at 44.1 kHz input', () => {
    const out = samplesOf(encodeAll(sine(10000, 44100, 1), 44100, 128));
    expect(rms(out)).toBeLessThan(0.02);
  });
});

describe('FrameChunker flush', () => {
  it('sends a tail of at least 20 ms and drops shorter ones', () => {
    const c = new FrameChunker();
    const frames: ArrayBuffer[] = [];
    c.push(new Float32Array(640 + 400), (f) => frames.push(f));
    expect(c.flush((f) => frames.push(f))).toBe(400);
    expect(frames.map((f) => f.byteLength)).toEqual([1280, 800]);
    c.push(new Float32Array(100), (f) => frames.push(f));
    expect(c.flush((f) => frames.push(f))).toBe(0);
    expect(frames).toHaveLength(2);
  });
});

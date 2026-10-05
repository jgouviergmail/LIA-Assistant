import { AVATAR_PCM_SAMPLE_RATE } from './types';

// Blackman-windowed sinc: fractional phase is carried across callback boundaries.
// 97 taps add at most 6 ms of look-ahead at the lowest supported input rate.
const HALF = 48;
const PHASES = 256;
const TAPS = HALF * 2 + 1;

function kernel(rate: number): Float64Array[] {
  const cutoff = Math.min(0.45, 7200 / rate);
  return Array.from({ length: PHASES }, (_, phase) => {
    const coefficients = new Float64Array(TAPS);
    let sum = 0;
    for (let tap = 0; tap < TAPS; tap++) {
      const x = tap - HALF - phase / PHASES;
      const sinc = x === 0 ? 2 * cutoff : Math.sin(2 * Math.PI * cutoff * x) / (Math.PI * x);
      const window =
        0.42 -
        0.5 * Math.cos((2 * Math.PI * tap) / (TAPS - 1)) +
        0.08 * Math.cos((4 * Math.PI * tap) / (TAPS - 1));
      coefficients[tap] = sinc * window;
      sum += coefficients[tap];
    }
    for (let tap = 0; tap < TAPS; tap++) coefficients[tap] /= sum;
    return coefficients;
  });
}

function encode(samples: readonly number[]): Uint8Array {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  samples.forEach((sample, index) => {
    const value = Math.max(-1, Math.min(1, sample));
    view.setInt16(index * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
  });
  return bytes;
}

export class Pcm16Resampler {
  private samples: number[] = [];
  private base = 0;
  private received = 0;
  private output = 0;
  private finished = false;
  private readonly coefficients: Float64Array[];
  constructor(readonly inputRate: number) {
    if (!Number.isInteger(inputRate) || inputRate < 8000 || inputRate > 96000) {
      throw new Error('voice_invalid_sample_rate');
    }
    this.coefficients = inputRate === AVATAR_PCM_SAMPLE_RATE ? [] : kernel(inputRate);
  }

  push(channels: readonly Float32Array[]): Uint8Array {
    if (this.finished) throw new Error('voice_resampler_finished');
    const frames = channels[0]?.length ?? 0;
    if (
      !channels.length ||
      channels.length > 8 ||
      frames > this.inputRate * 5 ||
      channels.some(channel => channel.length !== frames || channel.some(v => !Number.isFinite(v)))
    ) {
      throw new Error('voice_invalid_samples');
    }
    for (let i = 0; i < frames; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i] / channels.length;
      this.samples.push(sample);
    }
    this.received += frames;
    return this.drain(false);
  }

  finish(): Uint8Array {
    if (this.finished) return new Uint8Array();
    this.finished = true;
    const tail = this.drain(true);
    this.samples = [];
    return tail;
  }

  private drain(final: boolean): Uint8Array {
    const values: number[] = [];
    const ratio = this.inputRate / AVATAR_PCM_SAMPLE_RATE;
    const count = Math.floor((this.received * AVATAR_PCM_SAMPLE_RATE) / this.inputRate);
    while (this.output < count) {
      const position = this.output * ratio;
      const center = Math.floor(position);
      if (this.coefficients.length && !final && center + HALF >= this.received) break;
      let value = this.samples[center - this.base] ?? 0;
      if (this.coefficients.length) {
        const coefficients = this.coefficients[Math.floor((position - center) * PHASES)];
        value = 0;
        for (let tap = 0; tap < TAPS; tap++) {
          value += (this.samples[center - HALF + tap - this.base] ?? 0) * coefficients[tap];
        }
      }
      values.push(value);
      this.output++;
    }
    const discard = Math.max(
      0,
      Math.min(
        this.samples.length,
        Math.floor(this.output * ratio) - (this.coefficients.length ? HALF : 0) - this.base
      )
    );
    this.samples.splice(0, discard);
    this.base += discard;
    return encode(values);
  }
}

export function decodePcm16(data: ArrayBuffer): Float32Array {
  if (data.byteLength % 2) throw new Error('voice_invalid_pcm');
  const view = new DataView(data);
  const samples = new Float32Array(data.byteLength / 2);
  for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
  return samples;
}

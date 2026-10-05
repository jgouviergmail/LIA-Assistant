import { describe, expect, it } from 'vitest';
import { decodePcm16, Pcm16Resampler } from '../pcm-resampler';

function join(parts: readonly Uint8Array[]) {
  const bytes = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.length;
  }
  return bytes;
}
function convert(input: Float32Array, rate: number, chunk = input.length) {
  const resampler = new Pcm16Resampler(rate);
  const parts: Uint8Array[] = [];
  for (let offset = 0; offset < input.length; offset += chunk) {
    parts.push(resampler.push([input.subarray(offset, offset + chunk)]));
  }
  parts.push(resampler.finish());
  return join(parts);
}
function tone(rate: number, hz: number, amplitude = 0.3) {
  return Float32Array.from(
    { length: rate },
    (_, i) => amplitude * Math.sin((2 * Math.PI * hz * i) / rate)
  );
}
function rms(bytes: Uint8Array) {
  const samples = decodePcm16(bytes.slice().buffer).subarray(200, -200);
  return Math.sqrt(samples.reduce((sum, v) => sum + v * v, 0) / samples.length);
}

describe('continuous PCM16 mono resampling', () => {
  it.each([16000, 24000, 44100, 48000])(
    'keeps exact duration and bytes across irregular %i Hz chunks',
    rate => {
      const input = tone(rate, 900).subarray(0, rate - 13);
      const whole = convert(input, rate);
      expect(whole.length).toBe(Math.floor((input.length * 16000) / rate) * 2);
      expect(convert(input, rate, 137)).toEqual(whole);
    }
  );
  it('encodes little endian with clipping and mixes stereo without changing duration', () => {
    const resampler = new Pcm16Resampler(16000);
    expect(Array.from(resampler.push([new Float32Array([-2, -1, 0, 0.5, 1, 2])]))).toEqual([
      0, 128, 0, 128, 0, 0, 0, 64, 255, 127, 255, 127,
    ]);
    const stereo = new Pcm16Resampler(16000);
    expect(stereo.push([new Float32Array([0.3, -0.2]), new Float32Array([-0.3, 0.2])])).toEqual(
      new Uint8Array(4)
    );
  });
  it('attenuates frequencies above the target Nyquist instead of aliasing them into speech', () => {
    const inBand = rms(convert(tone(48000, 2000), 48000, 151));
    const alias = rms(convert(tone(48000, 12000), 48000, 151));
    expect(inBand).toBeGreaterThan(0.18);
    expect(alias / inBand).toBeLessThan(0.01);
  });
  it('preserves low energy, DC and an interior silence rather than filtering frames by volume', () => {
    const input = tone(24000, 1000, 0.0002);
    input.fill(0, 8000, 16000);
    const bytes = convert(input, 24000, 113);
    const samples = decodePcm16(bytes.slice().buffer);
    expect(samples.subarray(100, 5000).some(v => v !== 0)).toBe(true);
    expect(samples.subarray(5500, 10500).every(v => v === 0)).toBe(true);
    const dc = decodePcm16(convert(new Float32Array(24000).fill(0.2), 24000).slice().buffer);
    expect(dc[400]).toBeCloseTo(0.2, 4);
  });
  it.each([NaN, Infinity, 0, 1000, 96001])('refuses an invalid source rate %s', rate => {
    expect(() => new Pcm16Resampler(rate)).toThrow();
  });
  it('refuses malformed PCM and non-finite/mismatched channels before any write', () => {
    expect(() => decodePcm16(new ArrayBuffer(3))).toThrow();
    const converter = new Pcm16Resampler(24000);
    expect(() => converter.push([new Float32Array([NaN])])).toThrow();
    expect(() => converter.push([new Float32Array(2), new Float32Array(1)])).toThrow();
  });
  it('does not shift an impulse or retain a completed stream tail', () => {
    const input = new Float32Array(48000);
    input[24000] = 1;
    const output = decodePcm16(convert(input, 48000, 129).slice().buffer);
    let peak = 0;
    for (let i = 1; i < output.length; i++)
      if (Math.abs(output[i]) > Math.abs(output[peak])) peak = i;
    expect(peak).toBe(8000);
    const converter = new Pcm16Resampler(24000);
    expect(() => converter.push([new Float32Array(24000 * 5 + 1)])).toThrow();
    converter.push([new Float32Array(113)]);
    converter.finish();
    expect(converter.finish()).toHaveLength(0);
    expect(() => converter.push([new Float32Array(1)])).toThrow();
  });
});

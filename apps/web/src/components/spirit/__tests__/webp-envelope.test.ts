import { describe, expect, it } from 'vitest';
import { webpEnvelope } from './webp-envelope';

function animationContainer(durations: number[]) {
  const header = Buffer.alloc(12);
  header.write('RIFF');
  header.write('WEBP', 8);
  const frames = durations.map(duration => {
    const frame = Buffer.alloc(24);
    frame.write('ANMF');
    frame.writeUInt32LE(16, 4);
    frame.writeUIntLE(duration, 20, 3);
    return frame;
  });
  const container = Buffer.concat([header, ...frames]);
  container.writeUInt32LE(container.length - 8, 4);
  return container;
}

describe('WebP animation envelope', () => {
  it('measures the timeline from all frame durations, including holds', () => {
    expect(webpEnvelope(animationContainer([20, 900, 80]))).toMatchObject({
      frames: 3,
      durationMs: 1000,
    });
  });

  it('rejects a frame whose metadata header is truncated', () => {
    const container = animationContainer([20]).subarray(0, 34);
    container.writeUInt32LE(container.length - 8, 4);
    container.writeUInt32LE(14, 16);
    expect(() => webpEnvelope(container)).toThrow('WebP frame header is truncated');
  });
});

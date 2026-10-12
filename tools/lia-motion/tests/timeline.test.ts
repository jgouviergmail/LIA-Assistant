import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTimeline } from '../src/timeline.ts';

test('adjacent scenes have no gap and cuts align to the nearest musical beat', () => {
  const result = buildTimeline(
    [{ durationSeconds: 8.1 }, { durationSeconds: 11.7 }, { durationSeconds: 20.2 }],
    [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40],
    30
  );
  assert.deepEqual(
    result.map(({ from, durationInFrames }) => [from, durationInFrames]),
    [
      [0, 240],
      [240, 360],
      [600, 600],
    ]
  );
});

test('a distant beat does not consume a scene or move the editorial cut', () => {
  const result = buildTimeline([{ durationSeconds: 6 }, { durationSeconds: 7 }], [0, 20], 25);
  assert.deepEqual(
    result.map(({ from, durationInFrames }) => [from, durationInFrames]),
    [
      [0, 150],
      [150, 175],
    ]
  );
});

test('unsupported frame rate and invalid music coordinates are rejected', () => {
  assert.throws(() => buildTimeline([{ durationSeconds: 2 }], [0], 0), /frame rate/);
  assert.throws(() => buildTimeline([{ durationSeconds: 2 }], [0, Number.NaN], 30), /beats/);
});

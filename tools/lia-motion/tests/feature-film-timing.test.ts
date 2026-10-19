import assert from 'node:assert/strict';
import test from 'node:test';
import { frameForScene } from '../src/film/film-timing.ts';

const closeTo = (actual: number, expected: number, epsilon = 1e-8) =>
  assert.ok(Math.abs(actual - expected) < epsilon, `${actual} should equal ${expected}`);

test('chapter endpoints stay fixed for short, canonical and long cuts', () => {
  for (const duration of [468, 480, 485]) {
    for (const frame of [-40, 0]) assert.equal(frameForScene(frame, duration, 1679, [28.1], [53]), 0);
    for (const frame of [duration, duration + 40]) {
      assert.equal(frameForScene(frame, duration, 1679, [28.1], [53]), 480);
    }
    closeTo(frameForScene(duration / 2, duration, 1679, [], [53, 198, 305]), 240);
  }
});

test('authored actions land on the nearest global attacks within one rendered frame', () => {
  const duration = 485;
  const start = 1679;
  const actions = [53, 198, 305];
  const attackFrames = actions.map(action => Math.round(start + action * duration / 480) + 5);
  // Fractional onset seconds represent measured audio, not integer frame metadata.
  const onsets = attackFrames.map(attack => (attack + 0.16) / 60);
  for (let index = 0; index < actions.length; index++) {
    const localAttack = attackFrames[index] - start;
    closeTo(frameForScene(localAttack, duration, start, onsets, actions), actions[index]);
    const renderedCrossing = Array.from({ length: duration + 1 }, (_, frame) => frame)
      .find(frame => frameForScene(frame, duration, start, onsets, actions) >= actions[index]);
    assert.ok(renderedCrossing !== undefined);
    assert.ok(Math.abs(renderedCrossing + start - onsets[index] * 60) <= 1);
  }
});

test('nearest onset wins and equal-distance ties choose the earlier attack', () => {
  closeTo(frameForScene(103, 480, 200, [306 / 60, 303 / 60], [100]), 100);
  closeTo(frameForScene(97, 480, 200, [303 / 60, 297 / 60], [100]), 100);
});

test('an attack farther than eight frames leaves the original linear timing', () => {
  const duration = 468;
  const start = 728;
  const actualAction = 100 * duration / 480;
  const distantOnsets = [(start + actualAction + 9) / 60, 0, 200];
  for (const frame of [0, 12, actualAction, 170.5, 350, duration]) {
    closeTo(frameForScene(frame, duration, start, distantOnsets, [100]), frame * 480 / duration);
  }
});

test('the eight-frame snap limit is inclusive', () => {
  closeTo(frameForScene(108, 480, 0, [108 / 60], [100]), 100);
  assert.notEqual(frameForScene(109, 480, 0, [109 / 60], [100]), 100);
  // Rounding a measured attack must not pull an out-of-range onset into range.
  closeTo(frameForScene(108, 480, 0, [108.4 / 60], [100]), 108);
});

test('crowded anchors and endpoint-adjacent proposals are ignored safely', () => {
  const actions = [5, 100, 111, 170, 476];
  const onsets = [5 / 60, 104 / 60, 111 / 60, 170 / 60, 476 / 60];
  closeTo(frameForScene(104, 480, 0, onsets, actions), 100);
  // The second action still occurs, but its attack is seven frames from the prior anchor.
  assert.ok(frameForScene(111, 480, 0, onsets, actions) < 111);
  closeTo(frameForScene(170, 480, 0, onsets, actions), 170);
  closeTo(frameForScene(5, 480, 0, [5 / 60], [5]), 5);
  closeTo(frameForScene(476, 480, 0, [476 / 60], [476]), 476);
});

test('retimed clocks remain strictly increasing, finite and pass every action once', () => {
  const actions = [53, 106, 111, 164, 198, 218, 230, 275, 305, 334, 354];
  for (const duration of [468, 480, 485]) {
    const start = 2164;
    const onsets = actions.map((action, index) =>
      (Math.round(start + action * duration / 480) + (index % 2 ? -7 : 7)) / 60);
    const clock = Array.from({ length: duration + 1 }, (_, frame) =>
      frameForScene(frame, duration, start, onsets, actions));
    for (let index = 0; index < clock.length; index++) {
      assert.ok(Number.isFinite(clock[index]));
      assert.ok(clock[index] >= 0 && clock[index] <= 480);
      if (index > 0) assert.ok(clock[index] > clock[index - 1]);
    }
    for (const action of actions) {
      const crossings = clock.slice(1).filter((value, index) => clock[index] < action && value >= action);
      assert.equal(crossings.length, 1, `duration ${duration}, action ${action}`);
    }
  }
});

test('unordered duplicate and malformed events cannot introduce NaN or mutate inputs', () => {
  const onsets = [4.5, NaN, 2, Infinity, 2, -3, 1];
  const actions = [270, 120, NaN, 60, 120, Infinity, -1, 480, 900];
  const originalOnsets = [...onsets];
  const originalActions = [...actions];
  for (let frame = 0; frame <= 485; frame++) {
    const value = frameForScene(frame, 485, 0, onsets, actions);
    assert.ok(Number.isFinite(value));
    assert.ok(value >= 0 && value <= 480);
  }
  assert.deepEqual(onsets, originalOnsets);
  assert.deepEqual(actions, originalActions);
  assert.equal(frameForScene(NaN, 480, 0, onsets, actions), 0);
  assert.equal(frameForScene(-Infinity, 480, 0, onsets, actions), 0);
  assert.equal(frameForScene(Infinity, 480, 0, onsets, actions), 480);
  for (const duration of [0, -1, NaN, Infinity]) {
    assert.equal(frameForScene(100, duration, 0, onsets, actions), 0);
  }
  closeTo(frameForScene(100, 480, NaN, onsets, actions), 100);
});

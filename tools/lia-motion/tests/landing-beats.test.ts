import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { landingBeats } from '../src/film/landing-beats.ts';

test('dense percussion drives a calm cadence while every movement still lands on an attack', () => {
  const onsets = Array.from({ length: 40 }, (_, i) => .031 + i * .25);
  const beats = landingBeats(onsets);
  assert.equal(beats.length, 10);
  assert.ok(beats.every(([ms]) => onsets.some(t => Math.round(t * 1000) === ms)));
  assert.ok(beats.slice(1).every(([ms], i) => ms - beats[i][0] >= 900));
});

test('the actual 80 second score never makes the avatar jump more than once in 900 ms', () => {
  const score = JSON.parse(readFileSync(new URL('../public/audio/feature-film/score.json', import.meta.url), 'utf8'));
  const beats = landingBeats(score.transients.onsetTimesSeconds);
  assert.ok(beats.length >= 65 && beats.length <= 85);
  assert.ok(beats.slice(1).every(([ms], i) => ms - beats[i][0] >= 900));
  assert.ok(beats.slice(1).every(([ms], i) => ms - beats[i][0] <= 1500));
  assert.ok(beats.every(([ms]) => score.transients.onsetTimesSeconds.some((t: number) => Math.round(t * 1000) === ms)));
});

test('sparse music stays sparse and malformed or repeated attacks cannot create fast hops', () => {
  assert.deepEqual(landingBeats([]), []);
  const beats = landingBeats([NaN, -2, 0, .1, .1, 2, 4, Infinity]);
  assert.deepEqual(beats.map(b => b[0]), [0, 2000, 4000]);
});

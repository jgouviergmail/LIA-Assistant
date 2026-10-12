import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FULL_SCENES } from '../src/content.ts';
import {
  NATIVE_CAPTURES,
  PROOF_SHOTS,
  shotsForScene,
  timeChapterShots,
} from '../src/real-product-shots.ts';

test('every native full-film chapter keeps an exact contiguous frame partition', () => {
  for (const scene of FULL_SCENES) {
    const duration = Math.round(scene.durationSeconds * 25);
    const timed = timeChapterShots(scene, 17, duration);
    assert.equal(timed[0].from, 17);
    assert.equal(timed.at(-1)!.from + timed.at(-1)!.durationInFrames, 17 + duration);
    for (let index = 1; index < timed.length; index++) {
      assert.equal(timed[index].from, timed[index - 1].from + timed[index - 1].durationInFrames);
    }
    assert.ok(timed.every(entry => entry.durationInFrames > 0));
  }
});

test('the proof shows only native captures and rejects undocumented replacement shots', () => {
  for (const shot of PROOF_SHOTS.filter(shot => shot.kind === 'screen')) {
    assert.ok(NATIVE_CAPTURES[shot.assetId!]);
    assert.ok(NATIVE_CAPTURES[shot.assetId!].provenance.endsWith('manifest.json'));
    assert.equal('cursor' in shot, false);
  }
  assert.throws(() => shotsForScene('focus-not-captured'), /capture its real route/);
});

test('source-declared feature coverage never becomes screenshot proof implicitly', () => {
  const scene = FULL_SCENES.find(scene => scene.id === 'assistant-circle')!;
  const timed = timeChapterShots(scene, 0, 300);
  assert.ok(timed[0].declaredFeatureKeys.includes('peer_safety'));
  assert.equal(NATIVE_CAPTURES.relations.visibleFeatures.includes('peer_safety'), false);
});

test('internal native shot cuts use the measured music beats without creating gaps', () => {
  const beats = Array.from({ length: 21 }, (_, index) => index / 2);
  const timed = timeChapterShots(FULL_SCENES[0], 0, 270, undefined, beats, 30);
  assert.equal(timed.at(-1)!.from + timed.at(-1)!.durationInFrames, 270);
  for (const entry of timed.slice(0, -1)) {
    assert.ok(beats.some(at => Math.round(at * 30) === entry.from + entry.durationInFrames));
  }
});

test('invalid timing cannot silently create empty or non-finite native shots', () => {
  assert.throws(() => timeChapterShots(FULL_SCENES[0], 0, 1), /at least one frame/);
  assert.throws(
    () => timeChapterShots(FULL_SCENES[0], 0, 100, [{ id: 'bad', kind: 'type', weight: NaN }]),
    /finite and positive/
  );
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { FULL_SCENES, FOCUS_SCENES, FEATURE_LABELS } from '../src/content.ts';

const source = readFileSync(
  new URL('../../../apps/web/src/components/landing/editorial/chapters-data.ts', import.meta.url),
  'utf8'
);
const inventory = source.match(
  /export const REQUIRED_FEATURE_KEYS[^=]*=\s*\[([\s\S]*?)\]\s*as const/
);
const keys = [...(inventory?.[1] ?? '').matchAll(/'([^']+)'/g)].map(match => match[1]).sort();

test('the editorial source assigns every canonical public feature to an explicit beat', () => {
  assert.ok(keys.length > 0, 'canonical public inventory could not be read');
  const filmed = FULL_SCENES.flatMap(scene => scene.beats.flatMap(beat => beat.featureKeys));
  assert.deepEqual([...new Set(filmed)].sort(), keys);
  assert.deepEqual(Object.keys(FEATURE_LABELS).sort(), keys);
});

test('the editorial source preserves dedicated focuses for major feature families', () => {
  const kinds = new Set<string>(FOCUS_SCENES.map(scene => scene.kind));
  for (const kind of [
    'avatars',
    'radio',
    'relations',
    'meeting',
    'knowledge',
    'routine',
    'ecosystem',
    'health',
    'journal',
    'habits',
  ]) {
    assert.ok(kinds.has(kind), `missing dedicated demonstration: ${kind}`);
  }
});

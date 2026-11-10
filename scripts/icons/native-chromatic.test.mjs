import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { nativeArtwork, tintWithOriginalLuminance } from './native-chromatic.mjs';

const fluent = JSON.parse(fs.readFileSync(new URL('./vendor/fluent.json', import.meta.url)));

// Independent WCAG relative-luminance oracle, including known black/white anchors.
function luminance(color) {
  const digits = color.slice(1);
  const full = digits.length === 3 ? [...digits].map(value => value + value).join('') : digits;
  const values = full.match(/../g).map(value => parseInt(value, 16) / 255);
  const linear = values.map(value =>
    value < 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  );
  return linear.reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
}

function assertLuminancePreserved(source, painted) {
  assert.ok(
    Math.abs(luminance(source) - luminance(painted)) < 0.006,
    `Paint lost its native luminance: ${source} -> ${painted}`
  );
}

test('tint preserves dark, middle and light paints rather than flattening their contrast', () => {
  assert.equal(luminance('#000000'), 0);
  assert.equal(luminance('#ffffff'), 1);
  for (const source of ['#153771', '#3473ad', '#84bef2', '#ddeeff', '#ffcd0f']) {
    for (const hue of ['#2469A3', '#965BC2', '#AC454F']) {
      assertLuminancePreserved(source, tintWithOriginalLuminance(source, hue));
    }
  }
  // The previous uniform-color implementation must fail this same oracle.
  assert.throws(() => assertLuminancePreserved('#ddeeff', '#2469A3'));
  assert.throws(() => assertLuminancePreserved('#153771', '#E0CEED'));
});

test('native panel and foreground gradients retain their individual tonal separation', () => {
  for (const source of [
    'content_view',
    'text_bullet_list_square',
    'receipt',
    'image',
    'question_circle',
    'warning',
  ]) {
    const original = fluent[source].body;
    const painted = nativeArtwork('fluent', source, fluent[source]).body;
    const gradients = body =>
      new Map(
        [
          ...body.matchAll(
            /<(?:linear|radial)Gradient\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/(?:linear|radial)Gradient>/g
          ),
        ].map(match => [
          match[1],
          [...match[2].matchAll(/stop-color="(#[\da-f]{3,6})"/gi)].map(stop => stop[1]),
        ])
      );
    const after = gradients(painted);
    for (const [id, before] of gradients(original)) {
      assert.equal(after.get(id).length, before.length, `${source}/${id}`);
      before.forEach((color, index) => assertLuminancePreserved(color, after.get(id)[index]));
    }
  }
});

test('light punctuation remains readable instead of adopting the background gradient', () => {
  const question = nativeArtwork('fluent', 'question_circle', fluent.question_circle).body;
  assert.match(question, /stop-color="#fdfdfd"/);
  assert.match(question, /stop-color="#cceaff"/);
});

test('three-digit saturated colors are not misclassified as white foreground', () => {
  const artwork = {
    viewBox: '0 0 24 24',
    body: '<path d="M0 0h24v24H0z" fill="url(#paint)"/><defs><linearGradient id="paint"><stop stop-color="#f00"/><stop offset="1" stop-color="#f00"/></linearGradient></defs>',
  };
  const painted = nativeArtwork('fluent', 'fixture', artwork).body;
  assert.doesNotMatch(painted, /stop-color="#f00"/);
  const colors = [...painted.matchAll(/stop-color="(#[\da-f]{6})"/g)].map(match => match[1]);
  assert.equal(new Set(colors).size, 2);
});

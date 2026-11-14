import assert from 'node:assert/strict';
import { test } from 'node:test';

import { LIA_CONCEPTS } from './catalogue.mjs';
import { conceptArtwork } from './lia-artwork.mjs';

test('every declared concept owns a drawing in both colored styles', () => {
  const concepts = Object.entries(LIA_CONCEPTS);
  assert.ok(concepts.length > 0);
  for (const [name, concept] of concepts) {
    for (const style of ['fluent', 'flex']) {
      const artwork = conceptArtwork(name, concept.family, style);
      assert.equal(artwork.viewBox, '0 0 24 24');
      assert.match(artwork.body, /<(?:rect|path|circle) /);
    }
  }
});

test('a concept with no drawing or an unknown palette stops the generation', () => {
  // Falling through to the borrowed glyph would ship the line drawing as the object.
  assert.throws(() => conceptArtwork('Gramophone', 'communication', 'fluent'), /owns its drawing/);
  assert.throws(() => conceptArtwork('RadioSet', 'sepia', 'flex'), /Unknown paint family/);
});

test('the soft style shades a concept, the flat style paints plain inks', () => {
  assert.match(conceptArtwork('RadioSet', 'communication', 'fluent').body, /<linearGradient /);
  assert.doesNotMatch(conceptArtwork('RadioSet', 'communication', 'flex').body, /<linearGradient /);
});

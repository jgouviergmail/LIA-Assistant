import assert from 'node:assert/strict';
import { test } from 'node:test';

import { assertFacadeImports, readIconImports, sourceTokens } from './source-inventory.mjs';

test('the census follows aliases and ignores type-only declarations', () => {
  const imports = readIconImports(`
    import { Bell as Reminder, type LucideIcon } from '@/lib/icons';
    import type { LucideProps } from 'lucide-react';
    import { unrelated } from './elsewhere';
  `, 'fixture.tsx');
  assert.deepEqual(imports, [{ module: '@/lib/icons', name: 'Bell' }]);
  assert.doesNotThrow(() => assertFacadeImports(imports, 'fixture.tsx'));
});

test('a direct runtime import fails even when renamed locally', () => {
  const imports = readIconImports("import { Bell as Reminder } from 'lucide-react';", 'fixture.tsx');
  assert.throws(() => assertFacadeImports(imports, 'fixture.tsx'), /bypasses the account style/);
});

test('a namespace import cannot evade the facade guard', () => {
  const imports = readIconImports("import * as glyphs from 'lucide-react';", 'fixture.tsx');
  assert.deepEqual(imports, [{ module: 'lucide-react', name: '*' }]);
  assert.throws(() => assertFacadeImports(imports, 'fixture.tsx'), /bypasses the account style/);
});

test('formatting is immaterial but artwork and tree-shaking annotations are not', () => {
  const original = "export const icon = /*#__PURE__*/ createIcon({body: '<path />'});";
  const formatted = "export const icon = /*#__PURE__*/ createIcon({\n  body: '<path />'\n});";
  assert.equal(sourceTokens(original), sourceTokens(formatted));
  assert.notEqual(sourceTokens(original), sourceTokens(original.replace('<path />', '<circle />')));
  assert.notEqual(sourceTokens(original), sourceTokens(original.replace('/*#__PURE__*/', '')));
});

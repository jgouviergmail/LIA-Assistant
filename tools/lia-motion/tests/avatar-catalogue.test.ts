import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {AVATAR_CONTEXTS,AVATAR_GALLERY_CHARACTERS,AVATAR_PRESENTATION_CATALOGUE} from '../src/avatar-context.ts';

const native=(path:string)=>readFileSync(new URL(`../../../apps/web/${path}`,import.meta.url),'utf8');

function literalIds(source:string,name:string) {
  const array=source.match(new RegExp(`export const ${name} = \\[([\\s\\S]*?)\\] as const`));
  assert.ok(array,`native ${name} registry must remain readable`);
  return [...array[1].matchAll(/'([^']+)'/g)].map(match=>match[1]);
}

test('the film catalogue covers every currently selectable native avatar with its actual French name',()=>{
  const rigs=literalIds(native('src/components/eyes/eye-styles.ts'),'RIG_EYE_STYLE_IDS');
  const companions=literalIds(native('src/components/spirit/companion-catalogue.ts'),'COMPANION_CHARACTERS');
  const selected=[...rigs,...companions];
  const translations=JSON.parse(native('locales/fr/translation.json'));
  assert.deepEqual(AVATAR_PRESENTATION_CATALOGUE.map(character=>character.id),selected);
  assert.equal(new Set(selected).size,selected.length);
  for(const character of AVATAR_PRESENTATION_CATALOGUE) {
    assert.equal(character.name,translations.eyes.styles[character.id].name);
  }
});

test('BIP is represented once by the external guide while every other selectable style remains in the gallery',()=>{
  assert.equal(AVATAR_PRESENTATION_CATALOGUE.filter(character=>character.renderer==='mascot').length,1);
  assert.deepEqual(AVATAR_GALLERY_CHARACTERS.map(character=>character.id),AVATAR_PRESENTATION_CATALOGUE.filter(character=>character.id!=='bip').map(character=>character.id));
});

test('context accompaniment consistently addresses the spectator as tu',()=>{
  for(const context of AVATAR_CONTEXTS) {
    assert.doesNotMatch(`${context.title} ${context.detail}`,/\b(?:vous|votre|vos)\b/i);
  }
});

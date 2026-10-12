import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';

test('the illustrated install hint retains native French Chromium wording and remains an inert source projection',()=>{
  const translations=JSON.parse(readFileSync(new URL('../../../apps/web/locales/fr/translation.json',import.meta.url),'utf8'));
  const source=readFileSync(new URL('../src/FeatureScreens.tsx',import.meta.url),'utf8');
  const component=source.split('export function NativePwaMobile(')[1].split('function RelationCentralView')[0];
  assert.ok(component.includes(translations.dashboard.install_hint.text));
  assert.ok(component.includes(`>${translations.dashboard.install_hint.cta}</button>`));
  assert.doesNotMatch(component,/\b(?:fetch|apiClient|localStorage)\b|\.prompt\(|beforeinstallprompt/);
  const manifest=JSON.parse(readFileSync(new URL('../../../apps/web/public/manifest-fr.json',import.meta.url),'utf8'));
  assert.equal(manifest.display,'standalone');
});

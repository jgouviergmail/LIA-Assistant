import type { WorldPropIndex } from '../../src/features/world/prop-index';
import type { sortProps } from '../../src/features/world/prop-sort';
import type { actorOccluders } from '../../src/features/world/occlusion';
import type { paintHoverFootprint } from '../../src/features/world/art/hover';
import type { crystalAura, paintCrystalAura } from '../../src/features/world/art/crystal-aura';
import type { paintStars } from '../../src/features/world/art/stars';
import type { SpeechPainter, speechBox } from '../../src/features/world/art/speech';
import type { createSimulation } from '../../src/features/world/simulation';
/** Browser-only pixel oracle for the exact trusted procedural art modules. */
import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import ts from 'typescript';
import type { shadeSprite, nightStrength } from '../../src/features/world/art/lighting';
import type {
  paintAtmosphere,
  paintGroundShade,
  paintLampGlow,
  paintGroundLights,
} from '../../src/features/world/art/atmosphere';
import type { createCamera } from '../../src/features/world/geometry';
import type { paintProp, paintActor } from '../../src/features/world/art/props';
import type { paintFloor } from '../../src/features/world/art/floors';
import type { propTextureKey } from '../../src/features/world/art/prop-style';
import type { HOME_PALETTES } from '../../src/features/world/home-catalogue';
import type { DEFAULT_AVATAR } from '../../src/features/world/avatar-catalogue';
import type { WORLD } from '../../src/features/world/definition';

declare global {
  interface Window {
    worldArtOracle: {
      WorldPropIndex: typeof WorldPropIndex;
      sortProps: typeof sortProps;
      actorOccluders: typeof actorOccluders;
      paintHoverFootprint: typeof paintHoverFootprint;
      crystalAura: typeof crystalAura;
      paintCrystalAura: typeof paintCrystalAura;
      paintGroundShade: typeof paintGroundShade;
      paintStars: typeof paintStars;
      paintLampGlow: typeof paintLampGlow;
      paintGroundLights: typeof paintGroundLights;
      paintAtmosphere: typeof paintAtmosphere;
      createCamera: typeof createCamera;
      shadeSprite: typeof shadeSprite;
      nightStrength: typeof nightStrength;
      paintProp: typeof paintProp;
      paintActor: typeof paintActor;
      paintFloor: typeof paintFloor;
      propTextureKey: typeof propTextureKey;
      SpeechPainter: typeof SpeechPainter;
      speechBox: typeof speechBox;
      createSimulation: typeof createSimulation;
      avatar: typeof DEFAULT_AVATAR;
      world: typeof WORLD;
      palettes: typeof HOME_PALETTES;
    };
  }
}
export async function installArtOracle(page: Page): Promise<void> {
  const root = resolve(__dirname, '../../src/features/world');
  const modules = new Map<string, string>();
  function compile(name: string): void {
    if (modules.has(name)) return;
    const path = resolve(root, name);
    if (!path.startsWith(root + sep)) throw new Error('Art oracle outside trusted world source');
    modules.set(name, '');
    const source = readFileSync(path, 'utf8');
    let code = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    code = code.replace(/require\(["']([^"']+)["']\)/g, (_full, reference: string) => {
      if (!reference.startsWith('.')) throw new Error('Art oracle imported an external runtime');
      const dependency = relative(root, resolve(dirname(path), reference + '.ts')).replaceAll(
        '\\',
        '/'
      );
      compile(dependency);
      return `require(${JSON.stringify(dependency)})`;
    });
    modules.set(name, code);
  }
  for (const entry of [
    'prop-index.ts',
    'prop-sort.ts',
    'occlusion.ts',
    'art/hover.ts',
    'art/crystal-aura.ts',
    'art/stars.ts',
    'art/lighting.ts',
    'art/atmosphere.ts',
    'geometry.ts',
    'art/props.ts',
    'art/floors.ts',
    'art/prop-style.ts',
    'definition.ts',
    'avatar-catalogue.ts',
    'art/speech.ts',
    'simulation.ts',
    'home-catalogue.ts',
  ])
    compile(entry);
  const factories = [...modules]
    .map(([name, code]) => `${JSON.stringify(name)}:(module,exports,require)=>{${code}\n}`)
    .join(',');
  const script = `(()=>{const factories={${factories}},cache=Object.create(null);function require(name){if(cache[name])return cache[name].exports;const m={exports:{}};cache[name]=m;factories[name](m,m.exports,require);return m.exports}window.worldArtOracle={...require('prop-index.ts'),...require('prop-sort.ts'),...require('occlusion.ts'),...require('art/hover.ts'),...require('art/crystal-aura.ts'),...require('art/stars.ts'),...require('art/speech.ts'),...require('simulation.ts'),avatar:require('avatar-catalogue.ts').DEFAULT_AVATAR,...require('art/lighting.ts'),...require('art/atmosphere.ts'),...require('geometry.ts'),...require('art/props.ts'),...require('art/floors.ts'),...require('art/prop-style.ts'),world:require('definition.ts').WORLD,palettes:require('home-catalogue.ts').HOME_PALETTES}})();`;
  await page.route('**/world-art-oracle', route =>
    route.fulfill({
      contentType: 'text/html',
      headers: {
        'Content-Security-Policy':
          "default-src 'none'; script-src 'nonce-art-test'; style-src 'none'",
      },
      body: `<!doctype html><html lang="en"><title>Trusted art pixel oracle</title><body><script nonce="art-test">${script.replace(/<\/script/gi, '<\\/script')}</script></body></html>`,
    })
  );
  await page.goto('/world-art-oracle');
}

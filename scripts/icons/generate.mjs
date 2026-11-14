/** Reproduce the checked-in icon facade from pinned, trusted vendor geometry. */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  EXACT_CONTROL_REASONS,
  EXACT_CONTROLS,
  NATIVE_ABSENCE_REASONS,
  ICON_GROUPS,
  LIA_CONCEPTS,
  PALETTE_GROUPS,
} from './catalogue.mjs';
import { assertFacadeImports, readIconImports, sourceTokens } from './source-inventory.mjs';
import { conceptArtwork, liaArtwork } from './lia-artwork.mjs';
import { nativeArtwork } from './native-chromatic.mjs';
import { opticalViewBox } from './optical-framing.mjs';

const SCRIPT_ROOT = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_ROOT, '../..');
const WEB_ROOT = path.join(REPO_ROOT, 'apps/web');
const SOURCE_ROOT = path.join(WEB_ROOT, 'src');
const OUTPUT_ROOT = path.join(SOURCE_ROOT, 'lib/icons');
const checkOnly = process.argv.includes('--check');

/** Include migrated consumers as well as direct imports during the transition. */
function importedIconNames(directory) {
  const names = new Set();
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== '__tests__') {
        for (const name of importedIconNames(file)) names.add(name);
      }
      continue;
    }
    if (!/\.[jt]sx?$/.test(file) || /\.(test|spec)\./.test(file)) continue;
    if (file.startsWith(OUTPUT_ROOT + path.sep)) continue;
    const imports = readIconImports(fs.readFileSync(file, 'utf8'), file);
    if (checkOnly) assertFacadeImports(imports, file);
    for (const item of imports) names.add(item.name);
  }
  return names;
}

const vendor = Object.fromEntries(
  ['fluent', 'flex'].map(style => [
    style,
    JSON.parse(fs.readFileSync(path.join(SCRIPT_ROOT, `vendor/${style}.json`), 'utf8')),
  ])
);
const lucideGeometry = JSON.parse(
  fs.readFileSync(path.join(SCRIPT_ROOT, 'vendor/lucide.json'), 'utf8')
);
const liaRecipes = JSON.parse(fs.readFileSync(path.join(SCRIPT_ROOT, 'lia-recipes.json'), 'utf8'));
const paletteNames = new Map();
for (const [names, palette] of PALETTE_GROUPS) {
  for (const name of names.split(' ')) paletteNames.set(name, palette);
}
const declarations = new Map();
function declare(name, fluent, flex, reason) {
  if (declarations.has(name)) throw new Error(`Duplicate icon declaration: ${name}`);
  for (const [style, source] of Object.entries({ fluent, flex })) {
    if (source !== null && !vendor[style][source]) {
      throw new Error(`${name}: missing ${style} artwork ${source}`);
    }
  }
  declarations.set(name, { fluent, flex, reason });
}
for (const [names, fluent, flex] of ICON_GROUPS) {
  for (const name of names.split(' ')) {
    declare(name, fluent, flex);
  }
}
for (const name of EXACT_CONTROLS) {
  declare(
    name,
    null,
    null,
    EXACT_CONTROL_REASONS[name] ??
      'Preserve exact control, state or weather geometry; no equivalent in the pinned color sets.'
  );
}
const concepts = new Map(Object.entries(LIA_CONCEPTS));
for (const [name, concept] of concepts) declare(name, null, null, concept.reason);
const absenceReasons = new Map();
for (const [names, style, reason] of NATIVE_ABSENCE_REASONS) {
  for (const name of names.split(' ')) {
    if (!declarations.has(name) || declarations.get(name)[style] !== null) {
      throw new Error(
        `Native absence reason must describe a declared LIA complement: ${name}/${style}`
      );
    }
    const key = `${name}/${style}`;
    if (absenceReasons.has(key)) throw new Error(`Duplicate native absence reason: ${key}`);
    absenceReasons.set(key, reason);
  }
}
const imported = importedIconNames(SOURCE_ROOT);
// Type imports written before TypeScript introduced `import type` remain types.
for (const name of ['LucideIcon', 'LucideProps', 'IconNode']) imported.delete(name);
const missing = [...imported].filter(name => !declarations.has(name)).sort();
if (missing.length) throw new Error(`Undeclared icon imports: ${missing.join(' ')}`);
const names = [...declarations.keys()].sort();
const require = createRequire(path.join(WEB_ROOT, 'package.json'));
const lucide = require('lucide-react');
if (require('lucide-react/package.json').version !== lucideGeometry.version) {
  throw new Error('The LIA geometry snapshot must match the pinned Lucide version');
}
// The immutable geometry snapshot is independently checked against the installed,
// lockfile-pinned package; a local recipe cannot quietly rewrite its source.
const lucideRoot = path.dirname(require.resolve('lucide-react/package.json'));
const classNames = new Map();
for (const [name, snapshot] of Object.entries(lucideGeometry.icons)) {
  const { __iconData } = await import(
    pathToFileURL(path.join(lucideRoot, 'dist/esm', snapshot.source))
  );
  const node = __iconData.node.map(([tag, attributes]) => [
    tag,
    Object.fromEntries(Object.entries(attributes).filter(([key]) => key !== 'key')),
  ]);
  if (
    snapshot.name !== __iconData.name ||
    snapshot.size !== __iconData.size ||
    JSON.stringify(snapshot.node) !== JSON.stringify(node)
  ) {
    throw new Error(`Lucide geometry snapshot differs from the pinned source: ${name}`);
  }
  classNames.set(
    name,
    [
      'lucide',
      `lucide-${__iconData.name}`,
      ...(__iconData.aliases ?? []).map(alias => `lucide-${alias}`),
    ].join(' ')
  );
}
const aliases = new Map();
for (const name of names) {
  if (concepts.has(name)) {
    // A concept is its own drawing; the name must never shadow a Lucide glyph.
    if (lucide[name]) throw new Error(`LIA concept ${name} collides with a Lucide export`);
    aliases.set(name, name);
    continue;
  }
  const original = lucide[name];
  if (!original) throw new Error(`Lucide has no export named ${name}`);
  const sameComponent = names.filter(candidate => lucide[candidate] === original);
  const canonical = sameComponent.includes(original.displayName)
    ? original.displayName
    : sameComponent[0];
  aliases.set(name, canonical);
  const declaration = declarations.get(name);
  const canonicalDeclaration = declarations.get(canonical);
  if (
    declaration.fluent !== canonicalDeclaration.fluent ||
    declaration.flex !== canonicalDeclaration.flex
  ) {
    throw new Error(`Aliases ${name} and ${canonical} must share their artwork`);
  }
}
const canonicalNames = names.filter(name => aliases.get(name) === name);
for (const [name, concept] of concepts) {
  // The line style draws this glyph, so it must be a canonical facade icon.
  if (concepts.has(concept.lucide) || aliases.get(concept.lucide) !== concept.lucide) {
    throw new Error(`LIA concept ${name} needs a canonical Lucide glyph: ${concept.lucide}`);
  }
}
/** The Lucide glyph the line style draws for a facade name. */
const lucideGlyph = name => concepts.get(name)?.lucide ?? name;
const used = { fluent: new Map(), flex: new Map() };
const selections = new Map();
for (const name of canonicalNames) {
  const entry = declarations.get(name);
  const selection = {};
  for (const style of ['fluent', 'flex']) {
    const source = entry[style];
    const key = source ?? `lia_${name}`;
    if (!used[style].has(key)) {
      const artwork = concepts.has(name)
        ? conceptArtwork(name, concepts.get(name).family, style)
        : source === null
          ? liaArtwork(name, lucideGeometry.icons, liaRecipes[name], style)
          : nativeArtwork(style, source, vendor[style][source], paletteNames.get(source) ?? 'blue');
      used[style].set(key, {
        ...artwork,
        viewBox: opticalViewBox(artwork.viewBox, style, source, name),
      });
    }
    selection[style] = key;
  }
  selections.set(name, selection);
}

function constantName(style, source) {
  return `${style}_${source.replaceAll('-', '_')}`;
}

function artworkSource(style) {
  const lines = [
    `/** Trusted ${style} artwork and authored LIA complements. Generated by scripts/icons/generate.mjs. */`,
    `import type { IconArtwork } from '@/lib/icon-style';`,
    '',
  ];
  for (const source of [...used[style].keys()].sort()) {
    const artwork = used[style].get(source);
    const body = artwork.body
      .replaceAll('\\', '\\\\')
      .replaceAll("'", "\\'")
      .replaceAll('\n', '\\n');
    lines.push(
      `export const ${constantName(style, source)}: IconArtwork = {`,
      `  body: '${body}',`,
      `  viewBox: '${artwork.viewBox}',`,
      '};'
    );
  }
  return lines.join('\n') + '\n';
}

function facadeSource() {
  const lines = [
    "'use client';",
    '',
    '/** Application icon facade. Generated from the reviewed semantic catalogue. */',
    `import {\n${canonicalNames
      .filter(name => !concepts.has(name))
      .map(name => `  ${name} as Lucide${name},`)
      .join('\n')}\n} from 'lucide-react';`,
    "import { createAppIcon } from '@/components/icons/create-app-icon';",
    "export type { LucideIcon, LucideProps, IconNode } from 'lucide-react';",
  ];
  for (const style of ['fluent', 'flex']) {
    const imports = [...used[style].keys()].sort().map(source => constantName(style, source));
    lines.push(
      `import {\n${imports.map(name => `  ${name},`).join('\n')}\n} from './artwork-${style}';`
    );
  }
  lines.push('');
  for (const name of canonicalNames) {
    const selected = selections.get(name);
    const fluent = constantName('fluent', selected.fluent);
    const flex = constantName('flex', selected.flex);
    lines.push(
      `export const ${name} = /*#__PURE__*/ createAppIcon('${name}', Lucide${lucideGlyph(name)}, {`,
      `  fluent: ${fluent},`,
      `  flex: ${flex},`,
      `}, '${classNames.get(lucideGlyph(name))}');`
    );
  }
  for (const name of names.filter(name => aliases.get(name) !== name)) {
    lines.push(`export const ${name} = ${aliases.get(name)};`);
  }
  return lines.join('\n') + '\n';
}

const manifest = {};
for (const name of names) {
  const entry = declarations.get(name);
  if (concepts.has(name)) {
    // The drawing adapts no third-party geometry; only the line style borrows
    // a glyph, and that is what the entry records.
    manifest[name] = Object.fromEntries(
      ['fluent', 'flex'].map(style => [
        style,
        {
          source: `lia:${name}`,
          kind: 'lia-concept',
          lineStyle: {
            package: lucideGeometry.package,
            version: lucideGeometry.version,
            license: 'ISC',
            glyph: lucideGlyph(name),
            geometry: lucideGeometry.icons[lucideGlyph(name)].source,
          },
          palette: concepts.get(name).family,
          treatment: style === 'fluent' ? 'LIA Soft' : 'LIA Flat',
          reason: entry.reason,
        },
      ])
    );
    continue;
  }
  const canonical = aliases.get(name);
  manifest[name] = Object.fromEntries(
    ['fluent', 'flex'].map(style => [
      style,
      entry[style] === null
        ? {
            source: `lia:${canonical}`,
            kind: 'lia-complement',
            basedOn: {
              package: lucideGeometry.package,
              version: lucideGeometry.version,
              license: 'ISC',
              geometry: lucideGeometry.icons[canonical].source,
            },
            recipe: canonical,
            palette: liaRecipes[canonical].family,
            treatment: style === 'fluent' ? 'LIA Soft' : 'LIA Flat',
            reason:
              absenceReasons.get(`${name}/${style}`) ??
              (EXACT_CONTROLS.includes(name)
                ? entry.reason
                : `The pinned ${style === 'fluent' ? 'Fluent Color' : 'Flex Flat'} collection has no ${name} artwork preserving the same concept and state.`),
          }
        : {
            source: vendor[style][entry[style]].source,
            kind: 'native',
            correspondence: {
              applicationConcept: name,
              vendorConcept: entry[style],
              review: 'svg_geometry',
            },
            colorAdaptation:
              used[style].get(selections.get(canonical)[style]).adaptation ??
              'Original multicolor palette retained',
            ...(style === 'flex' ? { palette: paletteNames.get(entry[style]) ?? 'blue' } : {}),
          },
    ])
  );
}

const outputs = new Map([
  ['artwork-fluent.ts', artworkSource('fluent')],
  ['artwork-flex.ts', artworkSource('flex')],
  ['index.ts', facadeSource()],
]);
const lucideLicense = fs.readFileSync(
  path.join(path.dirname(require.resolve('lucide-react/package.json')), 'LICENSE'),
  'utf8'
);
const fluentLicense = fs.readFileSync(path.join(SCRIPT_ROOT, 'vendor/Fluent-LICENSE.txt'), 'utf8');
const notice = `LIA application icon attribution

Fluent System Icons by Microsoft — MIT
https://github.com/microsoft/fluentui-system-icons
Original geometry is retained. Achromatic or single-hue artwork is given an explicitly
adapted LIA multicolor palette. SVG identifiers are scoped at render time.

Flex Flat by Streamline, distributed through Iconify — CC BY 4.0
https://github.com/webalys-hq/streamline-vectors
https://creativecommons.org/licenses/by/4.0/
Changes: original color zones receive distinct chromatic LIA colors; single-tone
shapes receive a two-hue paint. Original geometry is unchanged.

Lucide Icons and Contributors — ISC, with the Feather-derived MIT icons listed below.
https://lucide.dev

LIA Soft and LIA Flat complements are authored adaptations of the pinned Lucide
geometry and command vocabulary. Separate surfaces, details, colored ribbons,
and state layers are painted by explicit recipes. These complements are LIA
artwork, not official Fluent Color or Streamline artwork. They replace missing
native concepts without a monochrome fallback. Lucide mode itself is unchanged.

An object none of these collections draws (the radio set) is drawn by LIA outright
in both colored styles and adapts no third-party geometry. Lucide mode keeps the
Lucide glyph the manifest names for it.

----- Microsoft license -----
${fluentLicense}
----- Lucide and Feather licenses -----
${lucideLicense}`.replaceAll('\r\n', '\n');
const noticePath = path.join(WEB_ROOT, 'public/icon-licenses.txt');
if (checkOnly) {
  if (
    !fs.existsSync(noticePath) ||
    fs.readFileSync(noticePath, 'utf8').replaceAll('\r\n', '\n') !== notice
  ) {
    throw new Error('Public icon attribution is stale');
  }
} else {
  fs.writeFileSync(noticePath, notice);
}
for (const [relative, content] of outputs) {
  const target = path.join(OUTPUT_ROOT, relative);
  if (checkOnly) {
    if (
      !fs.existsSync(target) ||
      sourceTokens(fs.readFileSync(target, 'utf8')) !== sourceTokens(content)
    ) {
      throw new Error(`Generated icon source is stale: ${target}`);
    }
  } else {
    fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
    fs.writeFileSync(target, content);
  }
}
const manifestPath = path.join(SCRIPT_ROOT, 'manifest.json');
const manifestText = JSON.stringify(manifest, null, 2) + '\n';
if (checkOnly) {
  if (fs.readFileSync(manifestPath, 'utf8') !== manifestText)
    throw new Error('Icon manifest is stale');
} else {
  fs.writeFileSync(manifestPath, manifestText);
}
const counts = Object.fromEntries(
  ['fluent', 'flex'].map(style => [
    style,
    {
      native: names.filter(name => declarations.get(name)[style] !== null).length,
      liaComplements: names.filter(
        name => declarations.get(name)[style] === null && !concepts.has(name)
      ).length,
      liaConcepts: concepts.size,
      monochromeFallback: 0,
      uniqueArtworks: used[style].size,
    },
  ])
);
console.log(
  JSON.stringify({ checkOnly, declared: names.length, imported: imported.size, ...counts })
);

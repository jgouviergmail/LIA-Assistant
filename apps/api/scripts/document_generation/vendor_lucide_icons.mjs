/**
 * Vendor the Lucide pictograms a generated presentation may carry (ADR-274).
 *
 * The backend draws a slide's icon from geometry it holds itself, never from the
 * network: this script copies the geometry of a CLOSED set of icons out of the
 * lucide-react package the web application already pins, with its version and its
 * ISC licence notice, into `src/domains/document_generation/lucide_icons.json`.
 *
 * Usage (from `apps/api`, after `pnpm install` in `apps/web`):
 *
 *     node scripts/document_generation/vendor_lucide_icons.mjs            # refresh the same set
 *     node scripts/document_generation/vendor_lucide_icons.mjs target ... # vendor exactly these
 *
 * The set is the schema's `SLIDE_ICONS`; `test_document_icons.py` holds the file
 * equal to it, so a name added to the vocabulary without its geometry, or the
 * reverse, reds the build.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const apiRoot = join(here, '..', '..');
const target = join(apiRoot, 'src', 'domains', 'document_generation', 'lucide_icons.json');
const lucide = join(apiRoot, '..', 'web', 'node_modules', 'lucide-react');

const requested = process.argv.slice(2);
const names = requested.length
  ? requested
  : Object.keys(JSON.parse(readFileSync(target, 'utf8')).icons);

const manifest = JSON.parse(readFileSync(join(lucide, 'package.json'), 'utf8'));
const licence = readFileSync(join(lucide, 'LICENSE'), 'utf8').split('\n---')[0].trim();

const icons = {};
for (const name of [...names].sort()) {
  const icon = await import(pathToFileURL(join(lucide, 'dist', 'esm', 'icons', `${name}.mjs`)).href);
  if (!icon.__iconData) {
    // A renamed icon survives as a module re-exporting its new name, with no data.
    throw new Error(`${name} is an alias in lucide-react@${manifest.version}: vendor its canonical name`);
  }
  // Each element keeps its tag and its geometry; React's `key` is not geometry.
  icons[name] = icon.__iconData.node.map(([tag, attributes]) => {
    const { key: _key, ...geometry } = attributes;
    return [tag, geometry];
  });
}

const vendored = {
  source: `lucide-react@${manifest.version}`,
  licence,
  icons,
};
writeFileSync(target, `${JSON.stringify(vendored, null, 2)}\n`, 'utf8');
console.log(`vendored ${Object.keys(icons).length} icons from lucide-react@${manifest.version}`);

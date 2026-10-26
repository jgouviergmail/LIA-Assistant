/* Compile trusted authored TypeScript, never user content. No package install. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../apps/web/node_modules/typescript');
const root = path.resolve(__dirname, '..');
function authored(name, dependencies = {}) {
  const source = fs.readFileSync(path.join(root, 'apps/web/src/features/world', name), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(js, {
    exports, Uint8Array, Int32Array,
    require(name) {
      if (!Object.hasOwn(dependencies, name)) throw new Error('Undeclared authored dependency: ' + name);
      return dependencies[name];
    },
  });
  return exports;
}
const authoring = authored('house-authoring.ts');
const layout = authored('house-layout.ts', { './house-authoring': authoring });
const world = authored('definition.ts', {
  './movement': authored('movement.ts'),
  './house-layout': layout,
  './house-furniture': authored('house-furniture.ts', { './house-authoring': authoring, './house-layout': layout, './wall-mounts': authored('wall-mounts.ts') }),
  './house-garden': authored('house-garden.ts', { './house-authoring': authoring, './house-layout': layout }),
}).WORLD;
const nav = authored('navigation.ts', { './route-smoothing': authored('route-smoothing.ts') }).compileNavigation(world);
const home = authored('home-catalogue.ts');
const avatar = authored('avatar-catalogue.ts');
const catalogues = {
  'avatar-v1.json': { version: 1, defaults: avatar.DEFAULT_AVATAR, hair: avatar.AVATAR_HAIR,
    colors: avatar.AVATAR_COLOR_IDS, skins: avatar.AVATAR_SKIN_IDS,
    outfits: avatar.AVATAR_OUTFITS, headwear: avatar.AVATAR_HEADWEAR },
  'campus-v1.json': { world, blocked: Array.from(nav.blocked), poses: authored('pose-slots.ts').compilePoseSlots(world) },
  'home-v1.json': { version: 1, palettes: home.HOME_PALETTES },
};
for (const [name, catalogue] of Object.entries(catalogues)) {
  const value = JSON.stringify(catalogue, null, 2) + '\n';
  const target = path.join(root, 'apps/api/src/domains/world/assets', name);
  if (process.argv.includes('--check')) {
    if (fs.readFileSync(target, 'utf8') !== value) {
      process.stderr.write('World server catalogue is stale. Run node scripts/world-catalogue.cjs\n');
      process.exitCode = 1;
    }
  } else fs.writeFileSync(target, value);
}

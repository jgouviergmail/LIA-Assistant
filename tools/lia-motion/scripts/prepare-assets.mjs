import { cp, mkdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const project = path.resolve(root, 'tools/lia-motion');
const source = path.resolve(root, 'apps/web/public');
await mkdir(path.resolve(project, 'public/audio'), { recursive: true });
for (const directory of ['avatars', 'fonts', 'screenshots/proof']) {
  const target = path.resolve(project, 'public', directory);
  await mkdir(path.dirname(target), { recursive: true });
  await cp(path.resolve(source, directory), target, { recursive: true });
}
await cp(path.resolve(source, 'icon.svg'), path.resolve(project, 'public/logo.svg'));
await stat(path.resolve(project, 'public/fonts/Inter-Variable.woff2'));
console.log('Native LIA assets prepared; original files remain the source of truth.');

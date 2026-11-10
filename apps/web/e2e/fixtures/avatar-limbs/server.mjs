/** Local-only visual bench: actual native components, no API or replacement renderer. */
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const directory = fileURLToPath(new URL('.', import.meta.url));
const app = fileURLToPath(new URL('../../../', import.meta.url));
const port = Number(process.env.AVATAR_BENCH_PORT ?? 5187);
if (!Number.isInteger(port) || port < 1 || port > 65535)
  throw new Error('Invalid local bench port');
const nativeScenes = {
  name: 'native-scene-controls',
  enforce: 'pre',
  transform(code, id) {
    if (!id.replaceAll('\\', '/').endsWith('/src/components/eyes/useEyesRig.ts')) return;
    const original = "from '@/components/eyes/rig/runtime'";
    if (!code.includes(original)) throw new Error('The native rig factory import has changed');
    return code.replace(original, `from '${directory.replaceAll('\\', '/')}native-scenes.ts'`);
  },
};
const server = await createServer({
  configFile: false,
  root: directory,
  publicDir: `${app}/public`,
  envDir: false,
  cacheDir: `${app}/../../.tmp/avatar-limbs-vite${port === 5187 ? '' : `-${port}`}`,
  plugins: [nativeScenes, react()],
  resolve: { alias: { '@': `${app}/src` } },
  define: { 'process.env.NODE_ENV': '"development"', 'process.env': '{}' },
  css: { postcss: { plugins: [] } },
  // Restart after source edits: a capture must not mix hot-reload generations.
  server: {
    host: '127.0.0.1',
    port,
    strictPort: true,
    hmr: false,
    watch: null,
    fs: { allow: [app] },
  },
});
await server.listen();
server.printUrls();
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, async () => {
    await server.close();
    process.exit(0);
  });
}

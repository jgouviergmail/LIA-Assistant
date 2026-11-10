/** Reuse the typed, hermetic World authority in the isolated Playwright container. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const [repo, output, baseUrl = 'http://127.0.0.1:3137'] = process.argv.slice(2);
if (!repo || !output || !['127.0.0.1', 'localhost'].includes(new URL(baseUrl).hostname))
  throw new Error('Use REPO OUTPUT LOCAL_URL');
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(packageRoot, 'package.json'));
const ts = require('typescript');
const compiled = path.join(packageRoot, 'world-compiled');
const options = {
  outDir: compiled,
  rootDir: path.join(repo, 'apps/web'),
  module: ts.ModuleKind.Node16,
  moduleResolution: ts.ModuleResolutionKind.Node16,
  target: ts.ScriptTarget.ES2022,
  strict: true,
  esModuleInterop: true,
  skipLibCheck: true,
  paths: {
    '@/*': [path.join(repo, 'apps/web/src/*')],
    zod: [path.join(packageRoot, 'node_modules/zod')],
    '@playwright/test': [path.join(packageRoot, 'node_modules/@playwright/test')],
  },
  typeRoots: [path.join(packageRoot, 'node_modules/@types')],
  types: ['node'],
};
const program = ts.createProgram(
  [path.join(repo, 'apps/web/e2e/capture/world-screenshot.ts')],
  options
);
const diagnostics = ts.getPreEmitDiagnostics(program);
if (diagnostics.length)
  throw new Error(
    ts.formatDiagnosticsWithColorAndContext(diagnostics, {
      getCanonicalFileName: n => n,
      getCurrentDirectory: () => packageRoot,
      getNewLine: () => '\n',
    })
  );
program.emit();
const { captureWorld } = require(path.join(compiled, 'e2e/capture/world-screenshot.js'));
const { chromium } = require('@playwright/test');
const browserDir = fs.readdirSync('/ms-playwright').find(n => /^chromium-\d+$/.test(n));
const browser = await chromium.launch({
  executablePath: `/ms-playwright/${browserDir}/chrome-linux64/chrome`,
  args: ['--disable-background-networking'],
});
fs.mkdirSync(output, { recursive: true });
const page = await browser.newPage({
  viewport: { width: 1600, height: 1050 },
  locale: 'en-US',
  timezoneId: 'Europe/Paris',
  serviceWorkers: 'block',
});
try {
  const report = await captureWorld(page, baseUrl, output);
  const bytes = fs.readFileSync(path.join(output, 'lia-world.jpg'));
  report.images = [
    {
      file: 'lia-world.jpg',
      width: 1600,
      height: 1050,
      sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    },
  ];
  report.capturedAt = new Date().toISOString();
  fs.writeFileSync(
    path.join(output, 'capture-report.json'),
    JSON.stringify(report, null, 2) + '\n'
  );
  console.log('Captured the real World with fictional people. Visual review required.');
} catch (error) {
  await page.screenshot({ path: path.join(output, 'failure.png') });
  console.error((await page.locator('body').innerText()).slice(0, 5000));
  throw error;
} finally {
  await browser.close();
}

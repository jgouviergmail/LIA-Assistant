/** Run inside the official Playwright container; capture and publication are separate. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [mode, repoArg, outputArg, baseUrl = 'http://127.0.0.1:3130'] = process.argv.slice(2);
if (!['capture', 'publish', 'validate', 'typecheck'].includes(mode) || !repoArg || !outputArg)
  throw new Error(
    'Usage: node run-public-screenshots.mjs capture|publish|validate|typecheck REPO OUTPUT [LOOPBACK_URL]'
  );
const repo = path.resolve(repoArg);
const output = path.resolve(outputArg);
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const execute = promisify(execFile);
const names = [
  'homepage',
  'chat',
  'chat-debug-panel',
  'chat-interactive-skills',
  'settings-preferences',
  'settings-features',
  'settings-features-memory',
  'settings-features-psyche',
  'settings-administration',
  'settings-administration-oneclick',
  'settings-administration-llm',
  'faq',
];
const legacyNames = {
  'chat-debug-panel': 'chat - debug panel',
  'chat-interactive-skills': 'chat - interactive skills',
  'settings-features-memory': 'settings-features - memory',
  'settings-features-psyche': 'settings-features - psyche',
};
const allNames = [...names, 'dashboard-wide', 'dashboard-narrow'];
const sha256 = buffer => crypto.createHash('sha256').update(buffer).digest('hex');
if (mode !== 'validate') fs.mkdirSync(output, { recursive: true });

function run(binary, args, options = {}) {
  return execFileSync(binary, args, { cwd: packageRoot, encoding: 'utf8', ...options });
}

function inspectImage(name) {
  const buffer = fs.readFileSync(path.join(output, `${name}.png`));
  if (!buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])))
    throw new Error(`Invalid PNG: ${name}`);
  return {
    file: `${name}.png`,
    sha256: sha256(buffer),
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

if (['capture', 'typecheck'].includes(mode)) {
  const url = new URL(baseUrl);
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:')
    throw new Error('Capture only the isolated local server, never a real deployment.');
  const compilerConfig = path.join(output, 'tsconfig.capture.json');
  fs.writeFileSync(
    compilerConfig,
    JSON.stringify(
      {
        compilerOptions: {
          outDir: path.join(output, 'compiled'),
          rootDir: path.join(repo, 'apps/web'),
          module: 'commonjs',
          moduleResolution: 'node',
          target: 'ES2022',
          strict: true,
          esModuleInterop: true,
          skipLibCheck: true,
          baseUrl: path.join(repo, 'apps/web'),
          paths: {
            '@/*': ['src/*'],
            '@playwright/test': [path.join(packageRoot, 'node_modules/@playwright/test')],
          },
          typeRoots: [path.join(packageRoot, 'node_modules/@types')],
          types: ['node'],
        },
        files: [
          path.join(repo, 'apps/web/e2e/capture/public-screenshots.ts'),
          path.join(repo, 'apps/web/e2e/fixtures/api-network-guard.ts'),
        ],
      },
      null,
      2
    )
  );
  const { default: ts } = await import(
    pathToFileURL(path.join(packageRoot, 'node_modules/typescript/lib/typescript.js')).href
  );
  const typeConfig = ts.readConfigFile(compilerConfig, ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(
    typeConfig.config,
    ts.sys,
    path.dirname(compilerConfig)
  );
  const programTypes = ts.createProgram(parsed.fileNames, parsed.options);
  const diagnostics = ts.getPreEmitDiagnostics(programTypes);
  if (diagnostics.length)
    throw new Error(
      ts.formatDiagnosticsWithColorAndContext(diagnostics, {
        getCanonicalFileName: name => name,
        getCurrentDirectory: () => packageRoot,
        getNewLine: () => '\n',
      })
    );
  programTypes.emit();
  if (mode === 'typecheck') {
    console.log('Public capture fixtures match the frontend contracts.');
    process.exit(0);
  }
  const skillFrame = JSON.parse(
    run('python3', [path.join(repo, 'apps/web/e2e/capture/render_trip_budget.py')], {
      input: JSON.stringify({ parameters: { _lang: 'en' } }),
    })
  ).frame;
  const nativeCards = JSON.parse(
    fs.readFileSync(path.join(repo, 'apps/web/e2e/fixtures/native-cards.json'), 'utf8')
  );
  for (const source of nativeCards.renderers) {
    if (sha256(fs.readFileSync(path.join(repo, source.source))) !== source.sha256)
      throw new Error(`Regenerate native card fixtures after changing ${source.source}`);
  }
  const { createCaptureCode } = await import(
    pathToFileURL(path.join(output, 'compiled/e2e/capture/public-screenshots.js')).href
  );
  const program = path.join(output, 'capture.js');
  const fontCss = fs.readFileSync(
    path.join(repo, 'apps/web/e2e/fixtures/fonts/material-symbols.css'),
    'utf8'
  );
  const fontPath = path.join(repo, 'apps/web/e2e/fixtures/fonts/MaterialSymbolsOutlined.woff2');
  fs.writeFileSync(
    program,
    createCaptureCode(baseUrl, output, skillFrame, nativeCards.publicAgendaHtml, fontCss, fontPath)
  );
  const { createApiNetworkGuard } = await import(
    pathToFileURL(path.join(output, 'compiled/e2e/fixtures/api-network-guard.js')).href
  );
  const guard = await createApiNetworkGuard();
  const browserDir = fs
    .readdirSync('/ms-playwright')
    .find(name => /^chromium_headless_shell-\d+$/.test(name));
  if (!browserDir) throw new Error('The official Playwright Chromium image is required.');
  const config = path.join(output, 'cli-config.json');
  fs.writeFileSync(
    config,
    JSON.stringify(
      {
        browser: {
          browserName: 'chromium',
          isolated: true,
          launchOptions: {
            executablePath: `/ms-playwright/${browserDir}/chrome-headless-shell-linux64/chrome-headless-shell`,
            args: [
              '--disable-background-networking',
              '--disable-component-update',
              '--disable-domain-reliability',
              '--disable-sync',
              '--disable-client-side-phishing-detection',
              '--safebrowsing-disable-auto-update',
              '--no-default-browser-check',
              '--no-first-run',
              '--no-pings',
              '--metrics-recording-only',
              '--disable-features=AutofillServerCommunication,CertificateTransparencyComponentUpdater,OptimizationHints,MediaRouter,Translate,NetworkTimeServiceQuerying',
            ],
            proxy: guard.proxy,
          },
          contextOptions: {
            locale: 'en-US',
            timezoneId: 'Europe/Paris',
            reducedMotion: 'no-preference',
            colorScheme: 'light',
            // Registration is disabled in our top-frame init script. Playwright's
            // block mode accesses navigator.serviceWorker in opaque skill frames.
            serviceWorkers: 'allow',
          },
        },
        outputDir: output,
      },
      null,
      2
    )
  );
  const cliArgs = [
    '--yes',
    '--package',
    '@playwright/cli@0.1.22',
    'playwright-cli',
    '--session',
    `public-screenshots-${process.pid}`,
  ];
  const cli = async args => {
    const { stdout: result } = await execute('npx', [...cliArgs, ...args], {
      cwd: packageRoot,
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
    });
    if (result.includes('### Error')) throw new Error(result);
    return result;
  };
  try {
    await cli(['open', 'about:blank', `--config=${config}`]);
    const result = await cli(['run-code', `--filename=${program}`]);
    fs.writeFileSync(path.join(output, 'capture-cli.log'), result);
    const match = result.match(/### Result\r?\n([\s\S]*?)\r?\n###/);
    if (!match) throw new Error('Missing Playwright capture result.');
    const report = JSON.parse(match[1]);
    report.capturedAt = new Date().toISOString();
    if (
      report.errors.length ||
      report.unexpected.length ||
      report.captures.length !== allNames.length ||
      allNames.some(name => !report.captures.some(capture => capture.name === name))
    )
      throw new Error('Incomplete or unsafe screenshot campaign.');
    report.images = allNames.map(inspectImage);
    report.transportGuard = { blockedRequests: guard.blockedRequests };
    if (guard.blockedRequests.length)
      throw new Error(`Unmocked transport blocked: ${JSON.stringify(guard.blockedRequests)}`);
    report.sourceCommit =
      process.env.LANDING_PROOF_SOURCE_COMMIT ??
      run('git', ['-C', repo, 'rev-parse', 'HEAD']).trim();
    report.sourceIncludesLocalChanges = /^(true|false)$/.test(
      process.env.LANDING_PROOF_LOCAL_CHANGES ?? ''
    )
      ? process.env.LANDING_PROOF_LOCAL_CHANGES === 'true'
      : null;
    fs.writeFileSync(
      path.join(output, 'capture-report.json'),
      JSON.stringify(report, null, 2) + '\n'
    );
    console.log(`Captured ${allNames.length} images. Inspect every image before publication.`);
  } catch (error) {
    try {
      fs.writeFileSync(
        path.join(output, 'capture-failure.log'),
        await cli([
          'run-code',
          `async page => { await page.screenshot({path:${JSON.stringify(path.join(output, 'capture-failure.png'))}}); return {url:page.url(),text:(await page.locator('body').innerText()).slice(0,12000)}; }`,
        ])
      );
    } catch {
      /* Preserve the original capture failure. */
    }
    throw error;
  } finally {
    guard.quarantine();
    try {
      await cli(['close']);
    } finally {
      await guard.close();
    }
  }
} else {
  const report = JSON.parse(fs.readFileSync(path.join(output, 'capture-report.json'), 'utf8'));
  if (
    report.errors.length ||
    report.unexpected.length ||
    report.images.length !== allNames.length ||
    !report.transportGuard ||
    report.transportGuard.blockedRequests.length
  )
    throw new Error('Publication requires a complete successful capture report.');
  const images = allNames.map(inspectImage);
  if (
    images.some(
      image =>
        !report.images.some(saved => saved.file === image.file && saved.sha256 === image.sha256)
    )
  )
    throw new Error('Images changed after capture validation.');
  const visualReview = JSON.parse(fs.readFileSync(path.join(output, 'visual-review.json'), 'utf8'));
  if (
    !images.every(image =>
      visualReview.images.some(
        review =>
          review.file === image.file && review.sha256 === image.sha256 && review.approved === true
      )
    )
  )
    throw new Error('Every final PNG requires its reviewed SHA-256');
  if (mode === 'validate') {
    console.log('Public campaign reports and image hashes validated without publication.');
    process.exit(0);
  }
  for (const name of names) {
    for (const destination of [
      `docs/assets/screenshot-${name}.png`,
      `apps/web/public/screenshots/${name}.png`,
      `apps/web/public/screenshots/v2/${legacyNames[name] ?? name}.png`,
    ])
      fs.copyFileSync(path.join(output, `${name}.png`), path.join(repo, destination));
  }
  for (const name of ['dashboard-wide', 'dashboard-narrow'])
    fs.copyFileSync(
      path.join(output, `${name}.png`),
      path.join(repo, `apps/web/public/screenshots/${name}.png`)
    );
  // The install previews declare the native dimensions of these same files.
  for (const file of fs
    .readdirSync(path.join(repo, 'apps/web/public'))
    .filter(name => /^manifest-[a-z]+\.json$/.test(name))) {
    const manifestPath = path.join(repo, 'apps/web/public', file);
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    for (const screenshot of manifest.screenshots ?? []) {
      const image = images.find(image => screenshot.src.endsWith(`/screenshots/${image.file}`));
      if (image) screenshot.sizes = `${image.width}x${image.height}`;
    }
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  }
  const revision = sha256(Buffer.from(images.map(image => image.sha256).join('\n'))).slice(0, 16);
  fs.writeFileSync(
    path.join(repo, 'apps/web/public/screenshots/manifest.json'),
    JSON.stringify(
      {
        revision,
        capturedAt: report.capturedAt,
        fixtureTime: report.fixtureTime,
        locale: 'en',
        theme: 'light',
        data: 'Fictional demonstration data only; no account or backend access.',
        sourceCommit: report.sourceCommit,
        sourceIncludesLocalChanges: report.sourceIncludesLocalChanges,
        transportGuard: report.transportGuard,
        avatar: {
          style: 'bip',
          variant: 'male',
          size: 'xl',
          gaze: 'Real pointer movements towards the centre and upper content; native motion enabled.',
          responsivePreview: 'The mobile PWA view preserves native avoidance and compaction.',
        },
        visualReview,
        images,
      },
      null,
      2
    ) + '\n'
  );
  console.log(`Updated README, landing and legacy copies. Revision: ${revision}`);
}

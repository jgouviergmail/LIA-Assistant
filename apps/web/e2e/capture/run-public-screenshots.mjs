/** Run inside the official Playwright container; capture and publication are separate. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [mode, repoArg, outputArg, baseUrl = 'http://127.0.0.1:3130'] = process.argv.slice(2);
if (!['capture', 'publish'].includes(mode) || !repoArg || !outputArg)
  throw new Error(
    'Usage: node run-public-screenshots.mjs capture|publish REPO OUTPUT [LOOPBACK_URL]'
  );
const repo = path.resolve(repoArg);
const output = path.resolve(outputArg);
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
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
fs.mkdirSync(output, { recursive: true });

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

if (mode === 'capture') {
  const url = new URL(baseUrl);
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:')
    throw new Error('Capture only the isolated local server, never a real deployment.');
  run(path.join(packageRoot, 'node_modules/.bin/tsc'), [
    'capture/public-screenshots.ts',
    '--outDir',
    path.join(output, 'compiled'),
    '--module',
    'commonjs',
    '--moduleResolution',
    'node',
    '--target',
    'ES2022',
    '--strict',
    '--esModuleInterop',
    '--skipLibCheck',
  ]);
  const game = JSON.parse(
    run('python3', [path.join(repo, 'data/skills/system/tic-tac-toe/scripts/render_game.py')], {
      input: JSON.stringify({ parameters: { _lang: 'en' } }),
    })
  ).frame.html;
  const { createCaptureCode } = await import(
    pathToFileURL(path.join(output, 'compiled/capture/public-screenshots.js')).href
  );
  const program = path.join(output, 'capture.js');
  fs.writeFileSync(program, createCaptureCode(baseUrl, output, game));
  const browserDir = fs.readdirSync('/ms-playwright').find(name => /^chromium-\d+$/.test(name));
  if (!browserDir) throw new Error('The official Playwright Chromium image is required.');
  const config = path.join(output, 'cli-config.json');
  fs.writeFileSync(
    config,
    JSON.stringify(
      {
        browser: {
          browserName: 'chromium',
          isolated: true,
          launchOptions: { executablePath: `/ms-playwright/${browserDir}/chrome-linux64/chrome` },
          contextOptions: {
            locale: 'en-US',
            timezoneId: 'Europe/Paris',
            reducedMotion: 'reduce',
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
    'public-screenshots',
  ];
  const cli = args => {
    const result = run('npx', [...cliArgs, ...args]);
    if (result.includes('### Error')) throw new Error(result);
    return result;
  };
  try {
    cli(['open', 'about:blank', `--config=${config}`]);
    const result = cli(['run-code', `--filename=${program}`]);
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
    report.sourceCommit = run('git', ['-C', repo, 'rev-parse', 'HEAD']).trim();
    report.sourceIncludesLocalChanges = Boolean(
      run('git', ['-C', repo, 'status', '--porcelain']).trim()
    );
    fs.writeFileSync(
      path.join(output, 'capture-report.json'),
      JSON.stringify(report, null, 2) + '\n'
    );
    console.log(`Captured ${allNames.length} images. Inspect every image before publication.`);
  } finally {
    cli(['close']);
  }
} else {
  const report = JSON.parse(fs.readFileSync(path.join(output, 'capture-report.json'), 'utf8'));
  if (report.errors.length || report.unexpected.length || report.images.length !== allNames.length)
    throw new Error('Publication requires a complete successful capture report.');
  const images = allNames.map(inspectImage);
  if (
    images.some(
      image =>
        !report.images.some(saved => saved.file === image.file && saved.sha256 === image.sha256)
    )
  )
    throw new Error('Images changed after capture validation.');
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
        images,
      },
      null,
      2
    ) + '\n'
  );
  console.log(`Updated README, landing and legacy copies. Revision: ${revision}`);
}

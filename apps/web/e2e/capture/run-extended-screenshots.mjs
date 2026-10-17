/** Isolated public screenshot extension. Run in the official Playwright container. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [mode, repoArg, outputArg, baseUrl = 'http://127.0.0.1:3130', selection] =
  process.argv.slice(2);
if (!['capture', 'publish', 'validate', 'typecheck'].includes(mode) || !repoArg || !outputArg)
  throw new Error(
    'Usage: node run-extended-screenshots.mjs capture|publish|validate|typecheck REPO OUTPUT [LOOPBACK_URL] [--only=avatar-picker,meetings-list]'
  );
const repo = path.resolve(repoArg);
const output = path.resolve(outputArg);
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const names = [
  'psyche',
  'psyche-evolution',
  'memory-library',
  'portrait',
  'routine-studio',
  'routine-week',
  'workboard',
  'workboard-dossier',
  'knowledge-library',
  'meeting-transcript',
  'meeting-templates',
  'connections',
  'skills-library',
  'model-routing',
  'consumption',
  'journal',
  'avatar-picker',
  'meetings-list',
];
const selectedNames = selection?.startsWith('--only=')
  ? selection.slice('--only='.length).split(',')
  : names;
if (
  selection &&
  (mode !== 'capture' ||
    !selection.startsWith('--only=') ||
    !selectedNames.length ||
    new Set(selectedNames).size !== selectedNames.length ||
    selectedNames.some(name => !['avatar-picker', 'meetings-list'].includes(name)))
)
  throw new Error(
    'Only the two new scenes may be captured independently: --only=avatar-picker,meetings-list'
  );
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const execute = promisify(execFile);
if (mode !== 'validate') fs.mkdirSync(output, { recursive: true });

function run(binary, args) {
  return execFileSync(binary, args, { cwd: packageRoot, encoding: 'utf8' });
}
function inspectImage(name) {
  const buffer = fs.readFileSync(path.join(output, `${name}.png`));
  if (!buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])))
    throw new Error(`Invalid PNG ${name}`);
  const image = {
    file: `${name}.png`,
    sha256: sha256(buffer),
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
  const height = ['psyche-evolution', 'knowledge-library'].includes(name)
    ? 820
    : ['avatar-picker', 'meetings-list'].includes(name)
      ? 1300
      : name === 'routine-studio'
        ? 1440
        : name === 'workboard'
          ? 900
          : 1100;
  if (image.width !== 1440 || image.height !== height) throw new Error(`Wrong viewport ${name}`);
  return image;
}

/** Read type declarations FROM current hooks; never load their React or API runtime. */
async function compileFixtures(compilerConfig) {
  const { default: ts } = await import(
    pathToFileURL(path.join(packageRoot, 'node_modules/typescript/lib/typescript.js')).href
  );
  const config = ts.readConfigFile(compilerConfig, ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, path.dirname(compilerConfig));
  const hooks = new Set(
    ['useMemories', 'useJournals', 'useScheduledActions', 'useSkills', 'useUserStatistics'].map(
      name => path.join(repo, `apps/web/src/hooks/${name}.ts`)
    )
  );
  const host = ts.createCompilerHost(parsed.options);
  const original = host.getSourceFile;
  const printer = ts.createPrinter();
  host.getSourceFile = (filename, languageVersion, onError, shouldCreateNewSourceFile) => {
    const full = path.resolve(filename);
    if (!hooks.has(full))
      return original(filename, languageVersion, onError, shouldCreateNewSourceFile);
    const source = ts.createSourceFile(
      filename,
      fs.readFileSync(filename, 'utf8'),
      languageVersion,
      true
    );
    const declarations = source.statements.filter(
      node =>
        ts.isInterfaceDeclaration(node) ||
        ts.isTypeAliasDeclaration(node) ||
        (ts.isImportDeclaration(node) && node.importClause?.isTypeOnly) ||
        (ts.isExportDeclaration(node) && node.isTypeOnly) ||
        (ts.isVariableStatement(node) &&
          node.declarationList.declarations.some(
            declaration =>
              ts.isIdentifier(declaration.name) && declaration.name.text === 'MEMORY_CATEGORIES'
          ))
    );
    return ts.createSourceFile(
      filename,
      declarations.map(node => printer.printNode(ts.EmitHint.Unspecified, node, source)).join('\n'),
      languageVersion,
      true
    );
  };
  const program = ts.createProgram(parsed.fileNames, parsed.options, host);
  const diagnostics = ts.getPreEmitDiagnostics(program);
  if (diagnostics.length)
    throw new Error(
      ts.formatDiagnosticsWithColorAndContext(diagnostics, {
        getCanonicalFileName: name => name,
        getCurrentDirectory: () => packageRoot,
        getNewLine: () => '\n',
      })
    );
  const result = program.emit();
  if (result.diagnostics.length) throw new Error('Capture fixture emit failed');
}

if (mode === 'capture' || mode === 'typecheck') {
  const url = new URL(baseUrl);
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:')
    throw new Error('Capture the isolated local server only');
  let previousReport;
  const retainedNames = names.filter(name => !selectedNames.includes(name));
  if (retainedNames.length) {
    previousReport = JSON.parse(fs.readFileSync(path.join(output, 'capture-report.json'), 'utf8'));
    if (
      previousReport.errors.length ||
      previousReport.unexpected.length ||
      previousReport.transportGuard.blockedRequests.length ||
      previousReport.locale !== 'en' ||
      previousReport.theme !== 'light' ||
      previousReport.avatar.size !== 'xl'
    )
      throw new Error('A targeted capture requires a successful reviewed existing campaign');
    const previousReview = JSON.parse(
      fs.readFileSync(path.join(output, 'visual-review.json'), 'utf8')
    );
    for (const name of retainedNames) {
      const image = inspectImage(name);
      if (
        !previousReport.images.some(
          saved => saved.file === image.file && saved.sha256 === image.sha256
        ) ||
        !previousReport.captures.some(saved => saved.name === name) ||
        !previousReview.images.some(
          review =>
            review.file === image.file &&
            review.sha256 === image.sha256 &&
            review.approved === true &&
            review.avatarPainted === true
        )
      )
        throw new Error(`Retained scene must keep its inspected original PNG: ${name}`);
    }
  }
  const compiled = path.join(output, 'compiled');
  const compilerConfig = path.join(output, 'capture-tsconfig.json');
  fs.writeFileSync(
    compilerConfig,
    JSON.stringify(
      {
        compilerOptions: {
          outDir: compiled,
          rootDir: path.join(repo, 'apps/web'),
          module: 'commonjs',
          moduleResolution: 'node',
          target: 'ES2022',
          strict: true,
          esModuleInterop: true,
          skipLibCheck: true,
          baseUrl: packageRoot,
          paths: {
            '@playwright/test': [path.join(packageRoot, 'node_modules/@playwright/test')],
            '@/*': [path.join(repo, 'apps/web/src/*')],
          },
          typeRoots: [path.join(packageRoot, 'node_modules/@types')],
          types: ['node'],
        },
        files: [
          path.join(repo, 'apps/web/e2e/capture/extended-screenshots.ts'),
          path.join(repo, 'apps/web/e2e/fixtures/api-network-guard.ts'),
        ],
      },
      null,
      2
    )
  );
  await compileFixtures(compilerConfig);
  if (mode === 'typecheck') {
    console.log(
      'Eighteen extended screenshot scenes checked against current application contracts.'
    );
    process.exit(0);
  }
  const { createExtendedCaptureCode } = await import(
    pathToFileURL(path.join(compiled, 'e2e/capture/extended-screenshots.js')).href
  );
  const { createApiNetworkGuard } = await import(
    pathToFileURL(path.join(compiled, 'e2e/fixtures/api-network-guard.js')).href
  );
  const copyRoot = JSON.parse(
    fs.readFileSync(path.join(repo, 'apps/web/locales/en/translation.json'), 'utf8')
  );
  const copy = {};
  function flatten(value, prefix = '') {
    for (const [key, item] of Object.entries(value)) {
      const name = prefix ? `${prefix}.${key}` : key;
      if (typeof item === 'string') copy[name] = item;
      else if (item && typeof item === 'object') flatten(item, name);
    }
  }
  flatten(copyRoot);
  // Pass only strings read by this programme, rather than the full locale corpus.
  const source = fs.readFileSync(
    path.join(repo, 'apps/web/e2e/capture/extended-screenshots.ts'),
    'utf8'
  );
  const usedCopy = Object.fromEntries(
    [...source.matchAll(/input\.copy\['([^']+)'\]/g)].map(([, key]) => {
      if (!copy[key]) throw new Error(`Missing current English copy ${key}`);
      return [key, copy[key]];
    })
  );
  const fontCss = fs.readFileSync(
    path.join(repo, 'apps/web/e2e/fixtures/fonts/material-symbols.css'),
    'utf8'
  );
  const fontPath = path.join(repo, 'apps/web/e2e/fixtures/fonts/MaterialSymbolsOutlined.woff2');
  const program = path.join(output, 'extended-capture-program.js');
  fs.writeFileSync(
    program,
    createExtendedCaptureCode(
      baseUrl,
      output,
      fontCss,
      fontPath,
      usedCopy,
      selection ? selectedNames : undefined
    )
  );
  const guard = await createApiNetworkGuard();
  const browserDir = fs
    .readdirSync('/ms-playwright')
    .find(name => /^chromium_headless_shell-\d+$/.test(name));
  if (!browserDir) throw new Error('Use the official Playwright Chromium container');
  const config = path.join(output, 'extended-capture-config.json');
  const chromeArgs = [
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
  ];
  fs.writeFileSync(
    config,
    JSON.stringify(
      {
        browser: {
          browserName: 'chromium',
          isolated: true,
          launchOptions: {
            executablePath: `/ms-playwright/${browserDir}/chrome-headless-shell-linux64/chrome-headless-shell`,
            args: chromeArgs,
            proxy: guard.proxy,
          },
          contextOptions: {
            locale: 'en-US',
            timezoneId: 'Europe/Paris',
            colorScheme: 'light',
            reducedMotion: 'no-preference',
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
    `extended-${process.pid}`,
  ];
  const cli = async args => {
    const { stdout } = await execute('npx', [...cliArgs, ...args], {
      cwd: packageRoot,
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
    });
    if (stdout.includes('### Error')) throw new Error(stdout);
    return stdout;
  };
  try {
    await cli(['open', 'about:blank', `--config=${config}`]);
    const result = await cli(['run-code', `--filename=${program}`]);
    fs.writeFileSync(path.join(output, 'capture-cli.log'), result);
    const match = result.match(/### Result\r?\n([\s\S]*?)\r?\n###/);
    if (!match) throw new Error('Missing extended capture result');
    const report = JSON.parse(match[1]);
    if (
      report.errors.length ||
      report.unexpected.length ||
      report.captures.length !== selectedNames.length ||
      selectedNames.some(name => !report.captures.some(capture => capture.name === name))
    )
      throw new Error('Incomplete or unsafe extended campaign');
    if (previousReport) {
      if (previousReport.fixtureTime !== report.fixtureTime)
        throw new Error('A targeted capture cannot mix demonstration clocks');
      report.captures = names.map(
        name =>
          report.captures.find(capture => capture.name === name) ??
          previousReport.captures.find(capture => capture.name === name)
      );
      report.mockedRequests = [
        ...new Set([...previousReport.mockedRequests, ...report.mockedRequests]),
      ];
      report.retainedCapture = {
        previousReportCapturedAt: previousReport.capturedAt,
        sourceCommit: previousReport.sourceCommit,
        images: previousReport.images
          .filter(image => retainedNames.includes(image.file.replace(/\.png$/, '')))
          .map(image => {
            const retained = previousReport.retainedCapture?.images.find(
              saved => saved.file === image.file && saved.sha256 === image.sha256
            );
            return {
              ...image,
              capturedAt: retained
                ? (retained.capturedAt ?? previousReport.retainedCapture.capturedAt)
                : previousReport.capturedAt,
            };
          }),
      };
    }
    report.images = names.map(inspectImage);
    report.capturedAt = new Date().toISOString();
    report.sourceCommit =
      process.env.LANDING_PROOF_SOURCE_COMMIT ??
      run('git', ['-C', repo, 'rev-parse', 'HEAD']).trim();
    report.sourceIncludesLocalChanges = /^(true|false)$/.test(
      process.env.LANDING_PROOF_LOCAL_CHANGES ?? ''
    )
      ? process.env.LANDING_PROOF_LOCAL_CHANGES === 'true'
      : null;
    report.browser = {
      engine: 'Chromium headless shell',
      directory: browserDir,
      backgroundNetworkingDisabled: true,
    };
    report.transportGuard = { blockedRequests: guard.blockedRequests };
    if (guard.blockedRequests.length)
      throw new Error(`Unmocked transport blocked: ${JSON.stringify(guard.blockedRequests)}`);
    fs.writeFileSync(
      path.join(output, 'capture-report.json'),
      JSON.stringify(report, null, 2) + '\n'
    );
    console.log(
      `Captured ${selectedNames.length} views; ${retainedNames.length} inspected PNGs retained unchanged. Review the new pixels before publication (${report.images.length} total).`
    );
  } catch (error) {
    try {
      const diagnostic = await cli([
        'run-code',
        `async page => { await page.screenshot({path:${JSON.stringify(path.join(output, 'capture-failure.png'))},timeout:20000}); return {url:page.url(), text:(await page.locator('body').innerText()).slice(0,20000)}; }`,
      ]);
      fs.writeFileSync(path.join(output, 'capture-failure.log'), diagnostic);
    } catch {
      /* Preserve the original failure. */
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
    report.transportGuard.blockedRequests.length ||
    report.captures.length !== names.length
  )
    throw new Error('Unsafe or incomplete extended capture report');
  const images = names.map(inspectImage);
  if (
    images.some(
      image =>
        !report.images.some(saved => saved.file === image.file && saved.sha256 === image.sha256)
    )
  )
    throw new Error('Images changed since capture validation');
  const visualReview = JSON.parse(fs.readFileSync(path.join(output, 'visual-review.json'), 'utf8'));
  if (
    !images.every(image =>
      visualReview.images.some(
        review =>
          review.file === image.file && review.sha256 === image.sha256 && review.approved === true
      )
    )
  )
    throw new Error('Every captured PNG must have a visual approval matching its SHA-256');
  if (mode === 'validate') {
    console.log(
      'Eighteen extended images, complete report, transport boundaries, hashes and visual approvals are valid.'
    );
    process.exit(0);
  }
  const destination = path.join(repo, 'apps/web/public/screenshots/proof');
  fs.mkdirSync(destination, { recursive: true });
  for (const name of names)
    fs.copyFileSync(path.join(output, `${name}.png`), path.join(destination, `${name}.png`));
  const revision = sha256(Buffer.from(images.map(image => image.sha256).join('\n'))).slice(0, 16);
  fs.writeFileSync(
    path.join(destination, 'extended-manifest.json'),
    JSON.stringify(
      {
        revision,
        capturedAt: report.capturedAt,
        fixtureTime: report.fixtureTime,
        locale: report.locale,
        theme: report.theme,
        viewport: report.viewport,
        avatar: report.avatar,
        data: 'Real application routes and controls with handwritten fictional demonstration data. No real account, backend, model, connector, billable call or external action was exercised.',
        sourceCommit: report.sourceCommit,
        sourceIncludesLocalChanges: report.sourceIncludesLocalChanges,
        browser: report.browser,
        transportGuard: report.transportGuard,
        retainedCapture: report.retainedCapture,
        visualReview,
        images,
        scenes: report.captures,
      },
      null,
      2
    ) + '\n'
  );
  console.log(`Published eighteen extended app views. Revision: ${revision}`);
}

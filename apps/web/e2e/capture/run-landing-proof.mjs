/** Run in the official Playwright container; review every PNG before publish. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [mode, repoArg, outputArg, baseUrl = 'http://127.0.0.1:3130'] = process.argv.slice(2);
if (!['capture', 'publish', 'typecheck'].includes(mode) || !repoArg || !outputArg)
  throw new Error('Usage: node run-landing-proof.mjs capture|publish|typecheck REPO OUTPUT [LOOPBACK_URL]');
const repo = path.resolve(repoArg);
const output = path.resolve(outputArg);
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const names = ['dossier', 'approval', 'knowledge', 'skill', 'memory', 'administration', 'relations', 'meetings', 'radio'];
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const execute = promisify(execFile);
fs.mkdirSync(output, { recursive: true });

function run(binary, args, options = {}) {
  return execFileSync(binary, args, { cwd: packageRoot, encoding: 'utf8', ...options });
}
function inspectImage(name) {
  const buffer = fs.readFileSync(path.join(output, `${name}.png`));
  if (!buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new Error(`Invalid PNG ${name}`);
  const image = { file: `${name}.png`, sha256: sha256(buffer), width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  if (image.width !== 1440 || image.height !== 960) throw new Error(`Wrong viewport ${name}`);
  return image;
}

async function compileFixtures(compilerConfig) {
  const { default: ts } = await import(pathToFileURL(path.join(packageRoot, 'node_modules/typescript/lib/typescript.js')).href);
  const config = ts.readConfigFile(compilerConfig, ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, path.dirname(compilerConfig));
  const hook = path.join(repo, 'apps/web/src/hooks/useRelations.ts');
  const source = ts.createSourceFile(hook, fs.readFileSync(hook, 'utf8'), ts.ScriptTarget.Latest, true);
  const definitions = new Map(source.statements.filter(node => ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node)).map(node => [node.name.text, node]));
  const required = new Set(['RelationContext', 'RelationDebrief', 'RelationDetail', 'RelationsOverview']);
  // Derive type-only declarations from the actual hook. Never copy business
  // implementations or hand-maintain a second wire contract in the runner.
  const visit = node => {
    if (ts.isTypeReferenceNode(node) && ts.isIdentifier(node.typeName) && definitions.has(node.typeName.text)) required.add(node.typeName.text);
    ts.forEachChild(node, visit);
  };
  for (const name of required) {
    const definition = definitions.get(name);
    if (!definition) throw new Error(`Missing real Relations contract ${name}`);
    visit(definition);
  }
  const printer = ts.createPrinter();
  const declarations = "import type { LLMUsage } from '../types/llm-usage';\n" + [...required].map(name => printer.printNode(ts.EmitHint.Unspecified, definitions.get(name), source)).join('\n');
  const fixture = path.join(repo, 'apps/web/e2e/capture/landing-proof-data.ts');
  const checks = { PROOF_RELATIONS: 'RelationsOverview', PROOF_RELATION: 'RelationDetail', PROOF_RELATION_CONTEXT: 'RelationContext', PROOF_RELATION_DEBRIEF: 'RelationDebrief' };
  let checkedFixture = `import type { ${Object.values(checks).join(', ')} } from '../../src/hooks/useRelations';\n` + fs.readFileSync(fixture, 'utf8');
  for (const [name, type] of Object.entries(checks)) {
    const declaration = `export const ${name} =`;
    if (!checkedFixture.includes(declaration)) throw new Error(`Missing Relations fixture ${name}`);
    checkedFixture = checkedFixture.replace(declaration, `export const ${name}: ${type} =`);
  }
  const host = ts.createCompilerHost(parsed.options);
  const original = host.getSourceFile;
  host.getSourceFile = (filename, languageVersion, onError, shouldCreateNewSourceFile) => {
    const full = path.resolve(filename);
    if (full === hook || full === fixture) return ts.createSourceFile(filename, full === hook ? declarations : checkedFixture, languageVersion, true);
    return original(filename, languageVersion, onError, shouldCreateNewSourceFile);
  };
  const program = ts.createProgram(parsed.fileNames, parsed.options, host);
  const result = program.emit();
  const diagnostics = [...ts.getPreEmitDiagnostics(program), ...result.diagnostics];
  if (diagnostics.length) throw new Error(ts.formatDiagnosticsWithColorAndContext(diagnostics, { getCanonicalFileName: name => name, getCurrentDirectory: () => packageRoot, getNewLine: () => '\n' }));
}

if (mode !== 'publish') {
  const url = new URL(baseUrl);
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:') throw new Error('Capture the isolated local server only');
  const compiled = path.join(output, 'compiled');
  const compilerConfig = path.join(output, 'capture-tsconfig.json');
  fs.writeFileSync(compilerConfig, JSON.stringify({ compilerOptions: { outDir: compiled, rootDir: path.join(repo, 'apps/web'), module: 'commonjs', moduleResolution: 'node', target: 'ES2022', strict: true, esModuleInterop: true, skipLibCheck: true, baseUrl: packageRoot, paths: { '@playwright/test': [path.join(packageRoot, 'node_modules/@playwright/test')] }, typeRoots: [path.join(packageRoot, 'node_modules/@types')], types: ['node'] }, files: [path.join(repo, 'apps/web/e2e/capture/landing-proof.ts'), path.join(repo, 'apps/web/e2e/fixtures/api-network-guard.ts')] }, null, 2));
  await compileFixtures(compilerConfig);
  if (mode === 'typecheck') {
    console.log('Landing proof capture types checked against the current frontend contracts.');
    process.exit(0);
  }
  const entry = path.join(compiled, 'e2e/capture/landing-proof.js');
  const guardEntry = path.join(path.dirname(path.dirname(entry)), 'fixtures/api-network-guard.js');
  const { createLandingProofCode } = await import(pathToFileURL(entry).href);
  const { createApiNetworkGuard } = await import(pathToFileURL(guardEntry).href);
  const converter = JSON.parse(run('python3', [path.join(repo, 'data/skills/system/unit-converter/scripts/render_converter.py')], { input: JSON.stringify({ parameters: { _lang: 'en' } }) })).frame;
  const fontCss = fs.readFileSync(path.join(repo, 'apps/web/e2e/fixtures/fonts/material-symbols.css'), 'utf8');
  const fontPath = path.join(repo, 'apps/web/e2e/fixtures/fonts/MaterialSymbolsOutlined.woff2');
  const program = path.join(output, 'landing-proof-program.js');
  // 120 seconds of unsigned 8-bit silence: exercise the player, never impersonate a voice.
  const silentAudioPath = path.join(output, 'landing-proof-silence.wav');
  const samples = 8000 * 120;
  const header = Buffer.alloc(44);
  header.write('RIFF'); header.writeUInt32LE(36 + samples, 4); header.write('WAVEfmt ', 8);
  header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
  header.writeUInt32LE(8000, 24); header.writeUInt32LE(8000, 28); header.writeUInt16LE(1, 32);
  header.writeUInt16LE(8, 34); header.write('data', 36); header.writeUInt32LE(samples, 40);
  fs.writeFileSync(silentAudioPath, Buffer.concat([header, Buffer.alloc(samples, 128)]));
  fs.writeFileSync(program, createLandingProofCode(baseUrl, output, converter, fontCss, fontPath, silentAudioPath));
  const guard = await createApiNetworkGuard();
  const browserDir = fs.readdirSync('/ms-playwright').find(name => /^chromium_headless_shell-\d+$/.test(name));
  if (!browserDir) throw new Error('Use the official Playwright Chromium container');
  const config = path.join(output, 'landing-proof-config.json');
  const chromeArgs = ['--disable-background-networking', '--disable-component-update', '--disable-domain-reliability', '--disable-sync', '--disable-client-side-phishing-detection', '--safebrowsing-disable-auto-update', '--no-default-browser-check', '--no-first-run', '--no-pings', '--metrics-recording-only', '--disable-features=AutofillServerCommunication,CertificateTransparencyComponentUpdater,OptimizationHints,MediaRouter,Translate,NetworkTimeServiceQuerying'];
  fs.writeFileSync(config, JSON.stringify({ browser: { browserName: 'chromium', isolated: true, launchOptions: { executablePath: `/ms-playwright/${browserDir}/chrome-headless-shell-linux64/chrome-headless-shell`, args: chromeArgs, proxy: guard.proxy }, contextOptions: { locale: 'en-US', timezoneId: 'Europe/Paris', reducedMotion: 'reduce', serviceWorkers: 'allow' } }, outputDir: output }, null, 2));
  // A fresh CLI session ensures revised launch flags do not reuse an old daemon.
  const cliArgs = ['--yes', '--package', '@playwright/cli@0.1.22', 'playwright-cli', '--session', `landing-proof-${process.pid}`];
  const cli = async args => {
    // Async spawn keeps the transport guard's server alive while Chromium runs.
    const { stdout } = await execute('npx', [...cliArgs, ...args], { cwd: packageRoot, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
    if (stdout.includes('### Error')) throw new Error(stdout);
    return stdout;
  };
  try {
    await cli(['open', 'about:blank', `--config=${config}`]);
    const result = await cli(['run-code', `--filename=${program}`]);
    fs.writeFileSync(path.join(output, 'capture-cli.log'), result);
    const match = result.match(/### Result\r?\n([\s\S]*?)\r?\n###/);
    if (!match) throw new Error('Missing capture result');
    const report = JSON.parse(match[1]);
    if (report.errors.length || report.unexpected.length || report.captures.length !== names.length || names.some(name => !report.captures.some(capture => capture.name === name))) throw new Error('Incomplete or unsafe campaign');
    report.images = names.map(inspectImage);
    report.capturedAt = new Date().toISOString();
    report.sourceCommit = process.env.LANDING_PROOF_SOURCE_COMMIT ?? run('git', ['-C', repo, 'rev-parse', 'HEAD']).trim();
    // Read this on the host: a full Git status on a Windows bind mount is slow
    // and leaves the browser open after all screenshots are already complete.
    report.sourceIncludesLocalChanges = /^(true|false)$/.test(process.env.LANDING_PROOF_LOCAL_CHANGES ?? '') ? process.env.LANDING_PROOF_LOCAL_CHANGES === 'true' : null;
    report.browser = { engine: 'Chromium headless shell', directory: browserDir, backgroundNetworkingDisabled: true };
    report.converter = { source: 'data/skills/system/unit-converter/scripts/render_converter.py', sourceSha256: sha256(fs.readFileSync(path.join(repo, 'data/skills/system/unit-converter/scripts/render_converter.py'))), emittedAspectRatio: converter.aspect_ratio, emittedHtmlSha256: sha256(Buffer.from(converter.html)) };
    report.transportGuard = { blockedRequests: guard.blockedRequests };
    if (guard.blockedRequests.length) throw new Error(`Unmocked transport blocked: ${JSON.stringify(guard.blockedRequests)}`);
    fs.writeFileSync(path.join(output, 'capture-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(`Captured ${report.images.length} real application views with fictional data; inspect every PNG before publication.`);
  } catch (error) {
    const diagnostic = `async page => { await page.screenshot({path:${JSON.stringify(path.join(output, 'capture-failure.png'))},timeout:20000}); const hasFrame = await page.locator('iframe.lia-skill-app-widget__iframe').count(); const frame = page.frameLocator('iframe.lia-skill-app-widget__iframe'); return {url:page.url(),categories:hasFrame ? await frame.locator('#cats').innerHTML().catch(()=>null) : null,units:hasFrame ? await frame.locator('#unit-from').innerHTML().catch(()=>null) : null,frames:page.frames().map(frame=>frame.url())}; }`;
    try { fs.writeFileSync(path.join(output, 'capture-failure.log'), await cli(['run-code', diagnostic])); } catch { /* Keep the original failure. */ }
    throw error;
  } finally {
    guard.quarantine();
    try { await cli(['close']); } finally { await guard.close(); }
  }
} else {
  const report = JSON.parse(fs.readFileSync(path.join(output, 'capture-report.json'), 'utf8'));
  if (report.errors.length || report.unexpected.length || report.transportGuard.blockedRequests.length) throw new Error('Unsafe app capture report');
  const images = names.map(inspectImage);
  if (images.some(image => !report.images.some(saved => saved.file === image.file && saved.sha256 === image.sha256))) throw new Error('Images changed since capture validation');
  const destination = path.join(repo, 'apps/web/public/screenshots/proof');
  fs.mkdirSync(destination, { recursive: true });
  for (const name of names) fs.copyFileSync(path.join(output, `${name}.png`), path.join(destination, `${name}.png`));
  const revision = sha256(Buffer.from(images.map(image => image.sha256).join('\n'))).slice(0, 16);
  fs.writeFileSync(path.join(destination, 'manifest.json'), JSON.stringify({ revision, capturedAt: report.capturedAt, fixtureTime: report.fixtureTime, locale: report.locale, theme: report.theme, viewport: report.viewport, avatar: report.avatar, data: 'Real frontend routes, handwritten fictional demonstration data. No account, backend, model or external action was exercised. Radio playback used only a local silent WAV; no generated voice was heard.', sourceCommit: report.sourceCommit, sourceIncludesLocalChanges: report.sourceIncludesLocalChanges, browser: report.browser, transportGuard: report.transportGuard, converter: report.converter, images, scenes: report.captures.map(({ name, route, exercised, illustrated, avatarDomBoundsInViewport }) => ({ name, route, exercised, illustrated, avatarDomBoundsInViewport })) }, null, 2) + '\n');
  console.log(`Published nine app proofs. Revision: ${revision}`);
}

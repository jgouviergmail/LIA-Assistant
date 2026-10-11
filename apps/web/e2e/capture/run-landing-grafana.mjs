/** Real local Grafana + provisioned LIA dashboards. Never production/provider access. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const [mode, repoArg, outputArg, baseUrl = 'http://lia-grafana-dev:3000'] = process.argv.slice(2);
if (!['capture', 'publish'].includes(mode) || !repoArg || !outputArg) throw new Error('Usage: node run-landing-grafana.mjs capture|publish REPO OUTPUT [LOCAL_GRAFANA_URL]');
const repo = path.resolve(repoArg);
const output = path.resolve(outputArg);
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const execute = promisify(execFile);
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const definitions = [
  { name: 'grafana-overview', source: 'infrastructure/observability/grafana/dashboards/01-app-overview.json', row: 'Request Performance' },
  { name: 'grafana-costs', source: 'infrastructure/observability/grafana/dashboards/05-llm-tokens-cost.json', row: 'Cost Breakdown' },
].map(definition => {
  const source = fs.readFileSync(path.join(repo, definition.source));
  const dashboard = JSON.parse(source);
  return { ...definition, uid: dashboard.uid, title: dashboard.title, sourceSha256: hash(source), dashboard };
});
fs.mkdirSync(output, { recursive: true });

async function capture(page, input) {
  const origin = new URL(input.baseUrl).origin;
  const blocked = [];
  const queryModes = [];
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { blocked.push(url.origin); await route.abort(); }
    else await route.continue();
  });
  await page.context().addCookies(input.cookies);

  const reply = body => {
    const results = {};
    for (const query of body.queries ?? []) {
      if (!query.refId) continue;
      const expression = (query.expr ?? '').toLowerCase();
      let base = 3.2;
      if (/availability/.test(expression)) base = 99.96;
      else if (/burn/.test(expression)) base = 0.23;
      else if (/budget/.test(expression)) base = 92;
      else if (/error|status_code.*5|status.*5/.test(expression)) base = 0.002;
      else if (/user_active|active_users|dau|wau/.test(expression)) base = /7d|week/.test(expression) ? 72 : 18;
      else if (/cost|eur|usd/.test(expression)) base = /conversation/.test(expression) ? 5.64 / 38 : /rate\(/.test(expression) ? 5.64 / 86400 : /1h/.test(expression) ? 0.04 : /7d/.test(expression) ? 27.9 : /lifetime/.test(expression) ? 184.5 : 5.64;
      else if (/conversation/.test(expression)) base = 38;
      else if (/tokens/.test(expression)) base = /rate\(/.test(expression) ? 340 : /lifetime/.test(expression) ? 8400000 : 420000;
      else if (/duration|latency|quantile/.test(expression)) base = 0.86;
      else if (/success|hit_ratio/.test(expression)) base = 0.987;
      const now = Number(body.to) || Date.now();
      const from = Number(body.from) || now - 6 * 3600000;
      const instant = query.instant === true;
      const count = instant ? 1 : 36;
      const times = Array.from({ length: count }, (_, index) => instant ? now : from + index * (now - from) / (count - 1));
      const timeSeries = /rate\(|duration|latency|quantile|conversation:cost/.test(expression);
      const values = Array.from({ length: count }, (_, index) => instant || !timeSeries ? base : base * (0.96 + 0.04 * Math.sin(index / 3)));
      const grouped = /by\s*\(|by_model|by_node/.test(expression);
      const byModel = /by_model|by\s*\(model\)/.test(expression);
      const variants = grouped ? (byModel ? ['gpt-4.1-mini', 'claude-sonnet-4-6', 'gpt-4.1'] : ['query_analyzer', 'planner', 'response']) : ['Demonstration'];
      results[query.refId] = { status: 200, frames: variants.map((label, index) => ({
        schema: { name: label, refId: query.refId, meta: { type: 'timeseries-multi', typeVersion: [0, 1] }, fields: [{ name: 'Time', type: 'time' }, { name: 'Value', type: 'number', labels: { llm_type: label.toLowerCase(), node_name: label, model: label, provider: 'demonstration', handler: ['/api/v1/agents/chat/stream', '/api/v1/briefing/cards', '/api/v1/agents/health'][index], route: label }, config: { displayNameFromDS: label } }] },
        data: { values: [times, values.map(value => value * (grouped ? [0.5, 0.3, 0.2][index] : 1))] },
      })) };
    }
    return { results };
  };
  await page.route('**/api/ds/query*', route => route.fulfill({ json: reply(route.request().postDataJSON()) }));
  const captures = [];
  for (const definition of input.definitions) {
    const dashboardUrl = `${input.baseUrl}/d/${definition.uid}/${definition.uid}?orgId=1&from=now-6h&to=now&timezone=utc&refresh=`;
    await page.goto(dashboardUrl, { waitUntil: 'domcontentloaded' });
    await page.getByText(definition.title, { exact: false }).first().waitFor({ timeout: 60000 });
    const row = page.getByText(definition.row, { exact: true }).first();
    await row.waitFor({ state: 'visible' });
    await row.click();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(4000);
    const empty = await page.getByText('No data', { exact: true }).filter({ visible: true }).count();
    const noData = await page.getByText('No data', { exact: true }).filter({ visible: true }).count();
    if (noData) throw new Error(`Dashboard ${definition.uid} still has ${noData} empty visible panels`);
    if (await page.getByText('An unexpected error happened', { exact: false }).count()) throw new Error('Grafana rendering failed');
    await page.mouse.move(0, 0);
    await page.screenshot({ path: `${input.output}/${definition.name}.png`, animations: 'disabled', caret: 'hide' });
    const data = 'Fictional demonstration metrics injected into the real provisioned Grafana query contract';
    queryModes.push({ name: definition.name, data, initiallyEmptyVisiblePanels: empty });
    captures.push({ name: definition.name, uid: definition.uid, route: new URL(page.url()).pathname, source: definition.source, sourceSha256: definition.sourceSha256, data, exercised: ['real Grafana dashboard route and row expansion', 'real Grafana panels rendering controlled query frames'], illustrated: ['all metric values, volumes and performance are fictional'] });
  }
  if (blocked.length) throw new Error('Grafana attempted an external origin');
  return { captures, queryModes, blocked, locale: 'en', theme: 'Grafana local default', viewport: { width: 1440, height: 960 } };
}

function inspectImage(name) {
  const buffer = fs.readFileSync(path.join(output, `${name}.png`));
  if (!buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new Error(`Invalid PNG ${name}`);
  const image = { file: `${name}.png`, sha256: hash(buffer), width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  if (image.width !== 1440 || image.height !== 960) throw new Error(`Wrong Grafana viewport ${name}`);
  return image;
}
if (mode === 'capture') {
  if (process.env.LANDING_GRAFANA_DEMO !== '1') throw new Error('Set LANDING_GRAFANA_DEMO=1; only fictional metric frames are permitted');
  const url = new URL(baseUrl);
  if (!['127.0.0.1', 'localhost', 'lia-grafana-dev'].includes(url.hostname) || url.protocol !== 'http:') throw new Error('Only local Grafana is authorized');
  // Authenticate outside the CLI sandbox. Password values never enter a
  // generated program or CLI output; its temporary session cookie is removed
  // with the program after capture and is never included in a report.
  const user = process.env.LANDING_GRAFANA_USER;
  const password = process.env.LANDING_GRAFANA_PASSWORD;
  if (!user || !password) throw new Error('Supply local Grafana credentials through LANDING_GRAFANA_USER/PASSWORD');
  const login = await fetch(`${baseUrl}/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user, password }) });
  if (!login.ok) throw new Error(`Local Grafana login failed (${login.status})`);
  const cookies = login.headers.getSetCookie().filter(cookie => cookie.startsWith('grafana_session=')).map(cookie => {
    const pair = cookie.split(';')[0];
    return { name: pair.slice(0, pair.indexOf('=')), value: pair.slice(pair.indexOf('=') + 1), domain: url.hostname, path: '/', httpOnly: true, sameSite: 'Lax' };
  });
  if (!cookies.length) throw new Error('Grafana did not issue its session cookie');
  const secrets = [user, password, ...cookies.map(cookie => cookie.value)];
  const browserDir = fs.readdirSync('/ms-playwright').find(name => /^chromium-\d+$/.test(name));
  if (!browserDir) throw new Error('Official Playwright image required');
  const config = path.join(output, 'grafana-cli-config.json');
  fs.writeFileSync(config, JSON.stringify({ browser: { browserName: 'chromium', isolated: true, launchOptions: { executablePath: `/ms-playwright/${browserDir}/chrome-linux64/chrome` }, contextOptions: { reducedMotion: 'reduce', timezoneId: 'UTC', locale: 'en-US' } }, outputDir: output }, null, 2));
  const program = path.join(output, 'grafana-capture-program.js');
  fs.writeFileSync(program, `async (page) => (${capture.toString()})(page, ${JSON.stringify({ baseUrl, output, definitions, cookies })})`);
  const cli = async args => {
    try {
      const { stdout } = await execute('npx', ['--yes', '--package', '@playwright/cli@0.1.22', 'playwright-cli', '--session', 'landing-grafana', ...args], { cwd: packageRoot, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
      if (stdout.includes('### Error')) throw new Error(stdout);
      return stdout;
    } catch (error) {
      let detail = error.stdout ?? error.message ?? 'Grafana capture failed';
      for (const secret of secrets) detail = detail.split(secret).join('[redacted]');
      throw new Error(detail);
    }
  };
  try {
    await cli(['open', 'about:blank', `--config=${config}`]);
    const result = await cli(['run-code', `--filename=${program}`]);
    const match = result.match(/### Result\r?\n([\s\S]*?)\r?\n###/);
    if (!match) throw new Error('Missing Grafana report');
    const report = JSON.parse(match[1]);
    report.images = definitions.map(definition => inspectImage(definition.name));
    report.capturedAt = new Date().toISOString();
    report.sourceCommit = execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    report.sourceIncludesLocalChanges = Boolean(execFileSync('git', ['-C', repo, 'status', '--porcelain'], { encoding: 'utf8' }).trim());
    fs.writeFileSync(path.join(output, 'grafana-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log('Captured two real provisioned Grafana dashboards; inspect images and metric provenance before publish.');
  } finally {
    fs.unlinkSync(program);
    await cli(['close']);
  }
} else {
  const report = JSON.parse(fs.readFileSync(path.join(output, 'grafana-report.json'), 'utf8'));
  const images = definitions.map(definition => inspectImage(definition.name));
  if (report.blocked.length || images.some(image => !report.images.some(saved => saved.file === image.file && saved.sha256 === image.sha256))) throw new Error('Unsafe or modified Grafana captures');
  const destination = path.join(repo, 'apps/web/public/screenshots/proof');
  fs.mkdirSync(destination, { recursive: true });
  for (const definition of definitions) fs.copyFileSync(path.join(output, `${definition.name}.png`), path.join(destination, `${definition.name}.png`));
  const revision = hash(Buffer.from(images.map(image => image.sha256).join('\n'))).slice(0, 16);
  fs.writeFileSync(path.join(destination, 'grafana-manifest.json'), JSON.stringify({ revision, capturedAt: report.capturedAt, locale: report.locale, theme: report.theme, viewport: report.viewport, sourceCommit: report.sourceCommit, sourceIncludesLocalChanges: report.sourceIncludesLocalChanges, images, scenes: report.captures }, null, 2) + '\n');
  console.log(`Published two Grafana proofs. Revision: ${revision}`);
}

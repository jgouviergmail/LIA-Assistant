/** One isolated native mobile capture. Reuses the audited V2 API fixtures and
 * browser-network guard; only the native widget visibility preference changes.
 * V2 assets/manifest are read-only. Run inside lia-motion-native-v2. */
import fs from 'node:fs';
import crypto from 'node:crypto';

const repo = '/repo';
const sourcePath = `${repo}/tools/lia-motion/scripts/capture-native.mjs`;
const source = fs.readFileSync(sourcePath, 'utf8');
const v2Manifest = `${repo}/tools/lia-motion/public/capture-v2/manifest.json`;
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const frozenManifestHash = hash(fs.readFileSync(v2Manifest));
let program = source;
function replaceOnce(from, to) {
  if (program.split(from).length !== 2) throw new Error(`Native capture contract drift: ${from.slice(0, 80)}`);
  program = program.replace(from, to);
}

replaceOnce("const output = '/repo/output/playwright/lia-motion-native-v2';", "const output = '/repo/output/playwright/lia-motion-native-v4';");
replaceOnce("const assetRoot = '/repo/tools/lia-motion/public/capture-v2';", "const assetRoot = '/repo/tools/lia-motion/public/capture-v4';");
replaceOnce('input.selected = process.argv.slice(2);', "input.selected = ['mobile'];");
replaceOnce("visible: true, style: 'bip', size: 'sm'", "visible: false, style: 'bip', size: 'sm'");
program = program.replaceAll('${assetRoot}/demo-files/', '${repo}/tools/lia-motion/public/capture-v2/demo-files/');
replaceOnce("'native mobile 390x844 chat and compact Bip companion, real responsive layout/composer/submission supplied fictional SSE tokens; no provider inference'", "'native mobile 390x844 chat, widget hidden through native persisted visibility preference; responsive composer/submission supplied fictional SSE tokens; no provider inference'");
const verification = `
      const companionProof = await page.evaluate(() => ({
        preferences: JSON.parse(localStorage.getItem('lia_eyes_widget_prefs') ?? 'null'),
        visibleBodies: [...document.querySelectorAll('[data-character="bip"], [data-spirit-companion]')].filter(element => {
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0 && getComputedStyle(element).visibility !== 'hidden';
        }).length,
      }));
      if (companionProof.preferences?.state?.visible !== false || companionProof.visibleBodies !== 0) throw new Error('A native companion remains visible on the mobile screen');
`;
replaceOnce("      await page.screenshot({ path: `${input.output}/${id}.png`, caret: 'hide' });", `${verification}\n      await page.screenshot({ path: \`\${input.output}/\${id}.png\`, caret: 'hide' });`);
replaceOnce('report.push({ id, route: urlPath, videoPath, clipStartSeconds, durationSeconds, exercised, errors, unexpected, writes });', 'report.push({ id, route: urlPath, videoPath, clipStartSeconds, durationSeconds, exercised, companionProof, errors, unexpected, writes });');

const manifestStart = program.indexOf('const manifestPath = `${assetRoot}/manifest.json`;');
if (manifestStart < 0) throw new Error('Native manifest contract drift');
program = program.slice(0, manifestStart) + `
const capture = report.find(item => item.id === 'mobile');
if (!capture || capture.failed) throw new Error(JSON.stringify(capture ?? report));
const still = \`\${assetRoot}/mobile.png\`;
fs.copyFileSync(\`\${output}/mobile.png\`, still);
const png = fs.readFileSync(still);
const provenance = {
  capturedAt: new Date().toISOString(),
  path: 'capture-v4/mobile.png',
  width: png.readUInt32BE(16), height: png.readUInt32BE(20),
  sha256: crypto.createHash('sha256').update(png).digest('hex'),
  nativeFrontend: true, reconstructed: false, bitmapEdited: false, fictionalData: true,
  route: capture.route, locale: 'fr-FR', viewport: { width: 390, height: 844 },
  runtime: 'existing isolated .next-e2e-landing-final standalone build in lia-web-dev, API fixtures only',
  currentRepositoryRevision: execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
  exactCompiledRevisionEstablished: false,
  sourceCaptureContract: 'tools/lia-motion/scripts/capture-native.mjs',
  widget: capture.companionProof,
  portraits: 'hidden by the native responsive layout at 390px, without product DOM or CSS replacement',
  exercised: capture.exercised, writes: capture.writes,
  transportGuardBlocked: guard.blockedRequests,
  errors: capture.errors, unexpected: capture.unexpected,
};
fs.writeFileSync(\`\${assetRoot}/mobile.provenance.json\`, JSON.stringify(provenance, null, 2) + '\\n');
console.log(JSON.stringify(provenance));
`;

await import(`data:text/javascript;base64,${Buffer.from(program).toString('base64')}`);
if (hash(fs.readFileSync(v2Manifest)) !== frozenManifestHash) throw new Error('The frozen V2 manifest changed during capture');
console.log('Frozen V2 manifest unchanged.');

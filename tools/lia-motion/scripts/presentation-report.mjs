/** Source-only handoff. No browser, render, media probe or provider call. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat, mkdir, readFile, readdir, realpath, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PRESENTATION_CHAPTERS, PRESENTATION_FOCUS_PLAN, MAIN_DECLARED_FEATURES,
  PRESENTATION_LANDING_CHAPTERS, PRESENTATION_REVISION,
} from '../src/presentation-plan.ts';
import { timePresentation } from '../src/presentation-timing.ts';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.resolve(root, 'exports/lia-motion');
const relative = file => path.relative(root, file).replaceAll(path.sep, '/');
const samePath = (a, b) => process.platform === 'win32'
  ? path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()
  : path.resolve(a) === path.resolve(b);

function localPath(file) {
  const resolved = path.resolve(root, file);
  const relation = path.relative(root, resolved);
  assert.ok(relation && !relation.startsWith('..') && !path.isAbsolute(relation), `Path outside workspace: ${file}`);
  return resolved;
}

async function fingerprint(file, role) {
  const target = localPath(file);
  const info = await lstat(target);
  assert.ok(info.isFile() && !info.isSymbolicLink(), `Expected a regular source file: ${file}`);
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(target)) hash.update(chunk);
  return { path: relative(target), role, bytes: info.size, sha256: hash.digest('hex') };
}

async function collectDirectory(directory, role, files) {
  const target = localPath(directory);
  const info = await lstat(target);
  assert.ok(info.isDirectory() && !info.isSymbolicLink(), `Expected a regular source directory: ${directory}`);
  for (const entry of await readdir(target, { withFileTypes: true })) {
    assert.ok(!entry.isSymbolicLink(), `Symbolic link excluded from source report: ${entry.name}`);
    const child = path.join(target, entry.name);
    if (entry.isDirectory()) await collectDirectory(relative(child), role, files);
    else if (entry.isFile()) files.set(relative(child), role);
  }
}

function canonicalInventory(source) {
  const match = source.match(/export const REQUIRED_FEATURE_KEYS:\s*readonly string\[\]\s*=\s*\[([\s\S]*?)\]\s*as const/);
  assert.ok(match, 'Canonical landing feature declaration is required');
  const keys = [...match[1].matchAll(/'([a-z_]+)'/g)].map(item => item[1]);
  assert.ok(keys.length > 0, 'Canonical feature inventory is empty');
  assert.equal(new Set(keys).size, keys.length, 'Canonical feature keys are unique');
  return keys;
}

/** The table supplies authored qualifications, not generated assertions. */
function editorialQualifications(markdown, canonical) {
  const rows = new Map();
  for (const line of markdown.split(/\r?\n/).filter(item => item.startsWith('| `focus-'))) {
    const cells = line.split('|').slice(1, -1).map(item => item.trim());
    const id = cells[0].match(/^`(focus-[a-z-]+)`$/)?.[1];
    assert.ok(id && cells.length === 3, 'Malformed coverage qualification row');
    const features = [...cells[1].matchAll(/`([a-z_]+)`/g)].map(item => item[1]);
    assert.ok(features.every(key => canonical.includes(key)), `Unknown documented key in ${id}`);
    assert.ok(!rows.has(id), `Duplicate qualification for ${id}`);
    rows.set(id, { features, qualification: cells[2] });
  }
  return rows;
}

function editorialOwnership(canonical, qualifications) {
  const owners = new Map();
  const known = new Set(canonical);
  for (const focus of PRESENTATION_FOCUS_PLAN) {
    for (const key of focus.features) assert.ok(known.has(key), `Unknown focus key ${key}`);
    if (!focus.coverageOwner) continue;
    const row = qualifications.get(focus.id);
    assert.ok(row, `Document the editorial qualification for ${focus.id}`);
    assert.deepEqual([...row.features].sort(), [...focus.features].sort(), `Coverage document drift: ${focus.id}`);
    for (const key of focus.features) {
      assert.ok(!owners.has(key), `Duplicate editorial owner for ${key}`);
      owners.set(key, focus.id);
    }
  }
  assert.deepEqual([...owners.keys()].sort(), [...canonical].sort(), 'Focus owners exactly partition the canonical inventory');
  for (const key of MAIN_DECLARED_FEATURES) assert.ok(known.has(key), `Unknown principal key ${key}`);
  return owners;
}

function timeline(chapters, beats, fps, compositionId, derivedTimingOnly = false) {
  const timed = timePresentation(chapters, beats, fps);
  const frames = timed.at(-1).start + timed.at(-1).duration;
  return {
    fps, compositionId, derivedTimingOnly,
    durationFrames: frames, durationSeconds: frames / fps,
    scope: 'Calculated source timing; not a measured encoded media duration.',
    chapters: timed.map(({ chapter, index, start, duration }) => ({
      id: chapter.id, index, kind: chapter.kind,
      fromFrame: start, untilFrameExclusive: start + duration, durationFrames: duration,
      fromSeconds: start / fps, untilSeconds: (start + duration) / fps,
      durationSeconds: duration / fps,
    })),
  };
}

function focusEdit(focus) {
  return [
    {
      ...focus, kind: focus.variant === 'conversation' ? 'context' : focus.variant === 'control' ? 'control' : focus.kind,
      durationSeconds: focus.durationSeconds - 4,
      direction: 'Focus indépendant sur la même interface native.', evidence: [],
    },
    { ...PRESENTATION_CHAPTERS.at(-1), durationSeconds: 4 },
  ];
}

async function writeReport(name, value) {
  const target = localPath(`exports/lia-motion/${name}`);
  assert.ok(samePath(path.dirname(target), output), 'Report target must stay in the media output directory');
  try {
    const existing = await lstat(target);
    assert.ok(existing.isFile() && !existing.isSymbolicLink(), 'Report target must be a regular file');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const working = localPath(`exports/lia-motion/${path.basename(name, '.json')}-working-${process.pid}.json`);
  await writeFile(working, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
  await rename(working, target);
}

async function main() {
  const inventorySource = 'apps/web/src/components/landing/editorial/chapters-data.ts';
  const qualificationSource = 'tools/lia-motion/coverage-v4.md';
  const [inventoryText, qualificationText, featureSource, musicText] = await Promise.all([
    readFile(localPath(inventorySource), 'utf8'), readFile(localPath(qualificationSource), 'utf8'),
    readFile(localPath('tools/lia-motion/src/FeatureScreens.tsx'), 'utf8'),
    readFile(localPath('tools/lia-motion/src/music-film.json'), 'utf8'),
  ]);
  const canonical = canonicalInventory(inventoryText);
  const qualifications = editorialQualifications(qualificationText, canonical);
  const owners = editorialOwnership(canonical, qualifications);
  const music = JSON.parse(musicText);
  const fullSeconds = PRESENTATION_CHAPTERS.reduce((sum, chapter) => sum + chapter.durationSeconds, 0);
  assert.ok(Number.isFinite(fullSeconds) && fullSeconds > 0, 'The principal has a finite positive duration');
  assert.ok(music.durationSeconds >= fullSeconds, 'The prepared soundtrack must cover the principal');
  const files = new Map();
  await collectDirectory('tools/lia-motion/src', 'production-source', files);
  for (const name of [
    'presentation-plan.ts', 'presentation-timing.ts', 'PresentationFilm.tsx', 'FeatureScreens.tsx',
    'presentation-film.css', 'feature-screens.css', 'product-story.css', 'Root.tsx', 'FaithfulUi.tsx',
    'ProductStory.tsx', 'StoryMascot.tsx', 'StoryLandingBackdrop.tsx', 'AvatarShowcase.tsx', 'music-film.json',
  ]) files.set(`tools/lia-motion/src/${name}`, 'active-source');
  for (const file of [
    'tools/lia-motion/README.md', 'tools/lia-motion/screenplay-v4.md', qualificationSource,
    'tools/lia-motion/scripts/presentation-report.mjs', 'tools/lia-motion/package.json',
    'tools/lia-motion/package-lock.json', 'Taskfile.yml', inventorySource,
  ]) files.set(file, 'editorial-and-rebuild-source');
  for (const match of featureSource.matchAll(/settingsSource\('([^']+)'\)/g))
    files.set(`apps/web/src/components/settings/${match[1]}.tsx`, 'native-ui-reference');
  for (const match of featureSource.matchAll(/['"]((?:apps\/web|infrastructure\/database\/seeds)\/[^'"]+)['"]/g))
    files.set(match[1], 'native-ui-reference');
  for (const file of [
    'apps/web/src/components/eyes/eye-styles.ts', 'apps/web/src/components/eyes/expression-engine.ts',
    'apps/web/src/components/eyes/monitor-geometry.ts', 'apps/web/src/lib/landing/beat-sync.ts',
    'apps/web/src/lib/landing/beats-schema.ts', 'apps/web/src/lib/landing/attention-background.ts',
    'apps/web/src/styles/globals.css', 'apps/web/src/styles/lia-components.css', 'apps/web/src/styles/eyes.css',
  ]) files.set(file, 'native-visual-and-timing-reference');
  for (const [directory, role] of [
    ['tools/lia-motion/public/capture-v2', 'native-reference-capture-or-fixture'],
    ['tools/lia-motion/public/capture-v4', 'active-native-mobile-capture'],
    ['tools/lia-motion/public/mascot-film', 'mascot-original-resource'],
    ['tools/lia-motion/public/avatars', 'prepared-native-avatar-resource'],
    ['tools/lia-motion/public/fonts', 'prepared-native-font-resource'],
    ['tools/lia-motion/public/audio/v3', 'music-original-and-license-evidence'],
    ['tools/lia-motion/public/audio/v4', 'historical-music-resource'],
    [path.posix.dirname(`tools/lia-motion/public/${music.audio}`), 'active-music-resource'],
    ['apps/web/src/components/eyes/rig', 'native-avatar-rig-source'],
    ['apps/web/src/components/eyes/smiley', 'native-avatar-expression-source'],
  ]) await collectDirectory(directory, role, files);
  const fingerprints = [];
  for (const [file, role] of [...files].sort(([a], [b]) => a.localeCompare(b)))
    fingerprints.push(await fingerprint(file, role));
  const hashes = new Map(fingerprints.map(item => [item.path, item.sha256]));
  const audioPath = `tools/lia-motion/public/${music.audio}`;
  assert.equal(hashes.get(audioPath), music.audioSha256, 'Working music matches its declared fingerprint');
  const sourceAudioPath = music.originalAudio
    ? `tools/lia-motion/public/${music.originalAudio}`
    : null;
  if (sourceAudioPath) {
    assert.ok(typeof music.sourceSha256 === 'string', 'A separate music original requires its declared fingerprint');
    assert.equal(hashes.get(sourceAudioPath), music.sourceSha256, 'Music original matches its declared fingerprint');
  }
  let recordedProviderGeneration = null;
  if (music.generationMetadata) {
    const recordPath = `tools/lia-motion/public/${music.generationMetadata}`;
    assert.ok(hashes.has(recordPath), 'Music creation metadata is included in the local fingerprints');
    const record = JSON.parse(await readFile(localPath(recordPath), 'utf8'));
    assert.equal(record.sourceSha256, music.sourceSha256, 'Music creation record identifies the preserved original');
    recordedProviderGeneration = {
      recordPath, recordSha256: hashes.get(recordPath), status: record.status,
      provider: record.provider, model: record.model,
      paidGenerationAttempts: record.paidGenerationAttempts,
      automaticRetries: record.automaticRetries,
      publishedGenerationPriceUsd: record.publishedGenerationPriceUsd,
      invoiceVerified: record.invoiceVerified === true,
      humanAudioAudition: record.humanAudioAudition === true,
      scope: 'Recorded soundtrack creation, distinct from product-feature provider execution; this report makes no API call.',
    };
  }
  const provenance = {
    version: 1, generation: PRESENTATION_REVISION, createdAt: new Date().toISOString(),
    scope: 'Editable source snapshot and editorial allocation. This generator does not render, probe or call providers; recorded soundtrack generation is documented separately. No visibility count or broadcaster acceptance is asserted.',
    validation: { editorialPartitionChecked: true, sourceFingerprintsCalculated: true, renderedMediaMeasured: false, visualReviewPerformed: false, providerExecutionPerformed: false, accountMutationPerformed: false },
    sources: { inventory: inventorySource, plan: 'tools/lia-motion/src/presentation-plan.ts', runtimeSelection: 'tools/lia-motion/src/PresentationFilm.tsx', screenContracts: 'tools/lia-motion/src/FeatureScreens.tsx', qualifications: qualificationSource },
    music: { title: music.title, artist: music.artist, source: music.source, provider: music.provider ?? null, model: music.model ?? null, license: music.license ?? null, licenseUrl: music.licenseUrl ?? null, attribution: music.attribution ?? null, rightsScope: 'Only the active music record establishes origin, terms and credit; no CC BY license or exclusive copyright is inferred for a commissioned provider creation.', declaredTempoBpm: music.tempoIsPromptTarget ? null : music.publishedTempoBpm ?? null, promptTempoTargetBpm: music.tempoIsPromptTarget ? music.publishedTempoBpm : null, beatScope: 'Measured musical cues; a published or prompted tempo is not a claim of constant effective onset tempo.', declaredWorkingDurationSeconds: music.durationSeconds, audioPath, audioSha256: music.audioSha256, sourceAudioPath, sourceSha256: sourceAudioPath ? music.sourceSha256 : null, sourceAudioFingerprintVerified: sourceAudioPath !== null, recordedProviderGeneration, encodedFilmAudioMeasured: false },
    fingerprints,
  };
  const coverage = {
    ...provenance,
    allocation: { canonicalFeatureCount: canonical.length, editorialOwnerCount: owners.size, principalDeclaredFeatureCount: MAIN_DECLARED_FEATURES.length, focusCompositionCount: PRESENTATION_FOCUS_PLAN.length, editorialPartitionExact: true, visibleFeatureCount: null, validatedClipCount: null, meaning: 'Editorial owners and main claims are not proof that every capability is visibly demonstrated.' },
    features: canonical.map(key => ({
      key, principalDeclared: MAIN_DECLARED_FEATURES.includes(key),
      principalChapters: PRESENTATION_CHAPTERS.filter(chapter => chapter.features.includes(key)).map(chapter => chapter.id),
      editorialOwner: owners.get(key),
      complementaryFocuses: PRESENTATION_FOCUS_PLAN.filter(focus => !focus.coverageOwner && focus.features.includes(key)).map(focus => focus.id),
      authoredQualification: qualifications.get(owners.get(key)).qualification,
      visuallyValidated: false, providerExecutionClaimed: false,
    })),
    limitations: {
      excalidraw: 'Editorially attributed and named; no Excalidraw editor or diagram is shown.',
      devops: 'Administration shows native users, model prices, LLM configuration and platform-health interfaces with fixtures; no DevOps CLI command or real diagnostic probe is executed.',
      documents: 'PDFs are local ReportLab filming fixtures, not LIA/provider generation.',
      cost: '0,001800 EUR is the fictional research-response usage, not a measured confirmation or provider charge.',
      settings: 'Configuration controls do not establish an active connection or executed service.',
      mobile: 'Native responsive web capture; no physical Android/iOS application, push delivery or two-client synchronization is certified.',
      simli: 'Experimental disconnected settings; no speaking avatar or provider session is shown.',
      avatars: 'Native animated characters and Lumo masculine use authored context changes; they do not certify live emotion inference or a speaking provider session.',
      notifications: 'The reminder notification is reconstructed with fixtures; no SSE, push or backend reminder delivery is exercised.',
      administration: 'Users, prices, LLM routing and platform states are controlled fixtures, not current instance values or saved changes.',
    },
  };
  const landing = PRESENTATION_LANDING_CHAPTERS;
  const screenplay = {
    ...provenance,
    timingScope: '30 fps matches the registered main/landing/focus composition prescriptions. 25 fps principal matches LIA-Master25; 25 fps landing/focus tables are derived editing aids, not registered or rendered compositions.',
    full: { chapters: PRESENTATION_CHAPTERS, timings: { fps30: timeline(PRESENTATION_CHAPTERS, music.beats, 30, 'LIA-Full'), fps25: timeline(PRESENTATION_CHAPTERS, music.beats, 25, 'LIA-Master25') } },
    landing: { chapters: landing, timings: { fps30: timeline(landing, music.beats, 30, 'LIA-Landing'), fps25: timeline(landing, music.beats, 25, null, true) } },
    focuses: PRESENTATION_FOCUS_PLAN.map(focus => ({
      ...focus, authoredQualification: qualifications.get(focus.id)?.qualification ?? focus.note ?? 'Authored complementary topic; no provider execution or account mutation is certified.',
      chapters: focusEdit(focus),
      timings: { fps30: timeline(focusEdit(focus), music.beats, 30, `LIA-${focus.id}`), fps25: timeline(focusEdit(focus), music.beats, 25, null, true) },
    })),
  };
  await mkdir(output, { recursive: true });
  const directory = await lstat(output);
  assert.ok(directory.isDirectory() && !directory.isSymbolicLink() && samePath(await realpath(output), output), 'Reports stay in the physical workspace export directory');
  await writeReport('presentation-coverage.json', coverage);
  await writeReport('screenplay-v4.json', screenplay);
  console.log(`${PRESENTATION_REVISION.toUpperCase()} editorial report: ${canonical.length} exact owners, ${MAIN_DECLARED_FEATURES.length} main claims, ${PRESENTATION_FOCUS_PLAN.length} focus prescriptions.`);
  console.log(`Source timing: full ${screenplay.full.timings.fps30.durationSeconds}s, landing ${screenplay.landing.timings.fps30.durationSeconds}s; ${fingerprints.length} local fingerprints. Media/provider validation is not asserted.`);
}

await main();

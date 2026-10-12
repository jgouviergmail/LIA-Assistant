import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FULL_SCENES, SHORT_SCENES, FOCUS_SCENES, FEATURE_LABELS } from '../src/content.ts';
import { buildTimeline } from '../src/timeline.ts';
import { NATIVE_CAPTURES, shotsForScene, timeChapterShots } from '../src/real-product-shots.ts';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.resolve(project, '../../exports/lia-motion');
const music: { beats: number[] } = JSON.parse(
  await readFile(path.resolve(project, 'src/music.json'), 'utf8')
);
await mkdir(output, { recursive: true });
const screenplay = buildTimeline(FULL_SCENES, music.beats, 30);
const nativeManifest = JSON.parse(await readFile(path.resolve(project, 'public/capture-v2/manifest.json'), 'utf8'));
const nativeAliases = nativeManifest.assets.some((asset: { id: string; beforePath?: string }) =>
  asset.id === 'chat' && asset.beforePath
) ? ['dossier-still'] : [];
const nativePlans = [...FULL_SCENES, ...FOCUS_SCENES.filter(scene => scene.status !== 'planned')].map(scene => ({
  scene: scene.id,
  shots: shotsForScene(scene.id),
  scope: 'Native frontend pixels and recorded demo interactions; no provider execution is implied.',
}));
const capturedFeature = (key: string) => nativeManifest.assets.filter((asset: { id: string }) =>
  NATIVE_CAPTURES[asset.id]?.visibleFeatures.includes(key as keyof typeof FEATURE_LABELS)
).map((asset: { id: string; path: string; clipPath?: string; locale: string; exercised?: string[]; scene?: { exercised?: string[] } }) => ({
  asset: asset.id,
  path: asset.clipPath ?? asset.path,
  kind: asset.clipPath ? 'recorded native interaction' : 'native screenshot',
  locale: asset.locale,
  exercised: asset.exercised ?? asset.scene?.exercised ?? [],
}));
const mapping = Object.entries(FEATURE_LABELS).map(([key, title]) => ({
  key,
  title,
  scope: 'Declared editorial scope; this alone does not mean the capability is visibly demonstrated.',
  nativeVisuals: capturedFeature(key),
  film: screenplay
    .filter(entry => entry.scene.featureKeys.includes(key as keyof typeof FEATURE_LABELS))
    .map(entry => ({ scene: entry.scene.id, fromSeconds: entry.from / 30 })),
  focuses: FOCUS_SCENES.filter(scene =>
    scene.featureKeys.includes(key as keyof typeof FEATURE_LABELS)
  ).map(scene => scene.id),
}));
await writeFile(path.resolve(output, 'native-shot-plan.json'), JSON.stringify({
  plans: nativePlans,
  full: screenplay.flatMap(({ scene, from, durationInFrames }) =>
    timeChapterShots(scene, from, durationInFrames, undefined, music.beats, 30)
  ),
  captures: nativeManifest.assets,
  missingAssets: [...new Set(nativePlans.flatMap(plan => plan.shots.flatMap(shot => shot.assetId ? [shot.assetId] : [])))].filter(id =>
    !nativeAliases.includes(id) && !nativeManifest.assets.some((asset: { id: string }) => asset.id === id)
  ),
}, null, 2) + '\n');
await writeFile(
  path.resolve(output, 'feature-coverage.json'),
  JSON.stringify(mapping, null, 2) + '\n'
);
await writeFile(
  path.resolve(output, 'screenplay.json'),
  JSON.stringify({ full: screenplay, short: SHORT_SCENES, focuses: FOCUS_SCENES }, null, 2) + '\n'
);
const rows = screenplay.map(
  ({ scene, from, durationInFrames }, index) =>
    `## ${index + 1}. ${scene.title}\n\n${(from / 30).toFixed(2)}–${((from + durationInFrames) / 30).toFixed(2)} s. ${scene.subtitle}\n\n${scene.beats.map(beat => `- ${beat.title} : ${beat.detail}`).join('\n')}\n\nSources : ${scene.evidence.join(', ')}\n`
);
await writeFile(
  path.resolve(output, 'storyboard.md'),
  `# LIA — scénario de production\n\nVersion française, musique seule. Données de démonstration fictives.\n\n${rows.join('\n')}`,
  'utf8'
);
console.log(`${mapping.length} editorial capabilities retained; native visual evidence is reported separately.`);

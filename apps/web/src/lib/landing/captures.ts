/**
 * The application captures the landing galleries show, and their static variants.
 *
 * The captures are proof campaigns: originals of 1,100 to 2,179 px, 0.35 to
 * 0.8 MB each, kept byte for byte for the full-screen view. The carousel used
 * to draw its thumbnails (80-96 CSS px), its ambient band (32 px) and its stage
 * from those originals — measured on the production landing on 2026-10-28,
 * sixteen of them (9.2 MB) arrived before the reader had scrolled at all. The
 * rail, the band and the stage now read WebP variants written ahead of time by
 * `apps/web/scripts/build-capture-variants.mjs` (2-3 KB a thumbnail, ~58 KB at
 * 1600 px), the pattern ADR-330 set for the blog illustrations: nothing is
 * resized on the host, and a file is cached at the edge by its extension. Only
 * the full-screen view still fetches the original.
 *
 * Imports nothing, on purpose: the generator loads this module through Node's
 * type stripping, so the views, the widths and the names it writes are the ones
 * the page reads. `__tests__/captures.guard.test.ts` refuses a missing or stale
 * variant.
 */

/** Where each capture campaign keeps its originals, as public paths. */
export const CAPTURE_CAMPAIGNS = {
  home: { directory: '/screenshots', extension: 'png' },
  application: { directory: '/screenshots/proof', extension: 'png' },
  extended: { directory: '/screenshots/proof', extension: 'png' },
  monitoring: { directory: '/screenshots/proof', extension: 'png' },
  world: { directory: '/screenshots/proof', extension: 'jpg' },
} as const;

export type CaptureCampaign = keyof typeof CAPTURE_CAMPAIGNS;

/** One view of a gallery: its translation key, its file stem and its campaign. */
export interface CaptureView {
  readonly key: string;
  readonly file: string;
  readonly campaign: CaptureCampaign;
}

// Follow the README's workflow groups, with libraries before their detail views.
// Capture campaigns describe provenance; they must not dictate browsing order.
export const APPLICATION_VIEWS = [
  { key: 'dashboard', file: 'dashboard-wide', campaign: 'home' },
  { key: 'dossier', file: 'dossier', campaign: 'application' },
  { key: 'relations', file: 'relations', campaign: 'application' },
  { key: 'radio', file: 'radio', campaign: 'application' },
  { key: 'places', file: 'places', campaign: 'application' },
  { key: 'maps', file: 'maps', campaign: 'application' },
  { key: 'routes', file: 'routes', campaign: 'application' },
  { key: 'memory_library', file: 'memory-library', campaign: 'extended' },
  { key: 'memory', file: 'memory', campaign: 'application' },
  { key: 'portrait', file: 'portrait', campaign: 'extended' },
  { key: 'avatar_picker', file: 'avatar-picker', campaign: 'extended' },
  { key: 'psyche', file: 'psyche', campaign: 'extended' },
  { key: 'psyche_evolution', file: 'psyche-evolution', campaign: 'extended' },
  { key: 'journal', file: 'journal', campaign: 'extended' },
  { key: 'routine_studio', file: 'routine-studio', campaign: 'extended' },
  { key: 'routine_week', file: 'routine-week', campaign: 'extended' },
  { key: 'workboard', file: 'workboard', campaign: 'extended' },
  { key: 'workboard_dossier', file: 'workboard-dossier', campaign: 'extended' },
  { key: 'knowledge_library', file: 'knowledge-library', campaign: 'extended' },
  { key: 'knowledge', file: 'knowledge', campaign: 'application' },
  { key: 'meetings_list', file: 'meetings-list', campaign: 'extended' },
  { key: 'meetings', file: 'meetings', campaign: 'application' },
  { key: 'meeting_transcript', file: 'meeting-transcript', campaign: 'extended' },
  { key: 'meeting_templates', file: 'meeting-templates', campaign: 'extended' },
  { key: 'approval', file: 'approval', campaign: 'application' },
  { key: 'connections', file: 'connections', campaign: 'extended' },
  { key: 'skills_library', file: 'skills-library', campaign: 'extended' },
  { key: 'skill', file: 'skill', campaign: 'application' },
  { key: 'model_routing', file: 'model-routing', campaign: 'extended' },
  { key: 'consumption', file: 'consumption', campaign: 'extended' },
  { key: 'administration', file: 'administration', campaign: 'application' },
] as const satisfies readonly CaptureView[];

export const MONITORING_VIEWS = [
  { key: 'grafana_overview', file: 'grafana-overview', campaign: 'monitoring' },
  { key: 'grafana_costs', file: 'grafana-costs', campaign: 'monitoring' },
  { key: 'grafana_activity', file: 'grafana-activity', campaign: 'monitoring' },
] as const satisfies readonly CaptureView[];

// Shown by their landing chapter alone, never repeated in the gallery.
export const CHAPTER_VIEWS = [
  { key: 'world', file: 'lia-world', campaign: 'world' },
] as const satisfies readonly CaptureView[];

/** A view a landing chapter can show on its own. */
export type ApplicationView = (typeof APPLICATION_VIEWS | typeof CHAPTER_VIEWS)[number]['key'];

/**
 * The thumbnails and the ambient band. A rail button is 80-96 CSS px wide;
 * 256 px keeps it sharp up to a 2.6x screen.
 */
export const CAPTURE_THUMB_WIDTH = 256;

/**
 * The stage candidates. The stage is capped at 1152 CSS px (`max-w-6xl`); most
 * captures are 1,100 to 1,600 px wide, and the wider ones (Grafana, the World)
 * stop at 1600 on the stage — the full-screen view keeps every original whole.
 */
export const CAPTURE_STAGE_WIDTHS = [640, 1024, 1600] as const;

/** The candidate a browser without `srcset` support loads. */
export const CAPTURE_STAGE_DEFAULT_WIDTH = 1024;

/** Every width the generator writes, smallest first. */
export const CAPTURE_VARIANT_WIDTHS = [CAPTURE_THUMB_WIDTH, ...CAPTURE_STAGE_WIDTHS] as const;

/** Where the variants live, as a public path. */
export const CAPTURE_VARIANTS_DIRECTORY = '/screenshots/variants';

/** The generator's record of the original each variant set was written from. */
export const CAPTURE_VARIANTS_MANIFEST = `${CAPTURE_VARIANTS_DIRECTORY}/manifest.json`;

/** Every view the landing can show (the guard holds each file to a single view). */
export function allCaptureViews(): readonly CaptureView[] {
  return [...APPLICATION_VIEWS, ...CHAPTER_VIEWS, ...MONITORING_VIEWS];
}

/**
 * A view's original file name, as its campaign manifest lists it.
 *
 * @param view - The view.
 * @returns The file name with its campaign's extension.
 */
export function captureFileName(view: CaptureView): string {
  return `${view.file}.${CAPTURE_CAMPAIGNS[view.campaign].extension}`;
}

/**
 * Public path of a view's original.
 *
 * @param view - The view.
 * @returns The original's path under `public/`.
 */
export function captureOriginalPath(view: CaptureView): string {
  return `${CAPTURE_CAMPAIGNS[view.campaign].directory}/${captureFileName(view)}`;
}

/**
 * Public path of one WebP variant.
 *
 * @param file - The view's file stem.
 * @param width - One of {@link CAPTURE_VARIANT_WIDTHS}.
 * @returns The variant's path under `public/`.
 */
export function captureVariantPath(file: string, width: number): string {
  return `${CAPTURE_VARIANTS_DIRECTORY}/${file}-${width}.webp`;
}

/**
 * The stage's `srcset`. The generator never enlarges an original, so a
 * candidate's descriptor is the width it actually HAS: a 1100-px capture's
 * `-1600` file is announced as `1100w`, and a width two candidates would share
 * is listed once.
 *
 * @param file - The view's file stem.
 * @param nativeWidth - The original's width, when its campaign records it.
 * @param query - The cache-busting query every path carries (`?v=<revision>`).
 * @returns The `srcset` attribute.
 */
export function captureStageSrcSet(
  file: string,
  nativeWidth: number | undefined,
  query: string
): string {
  const announced = new Set<number>();
  const candidates: string[] = [];
  for (const width of CAPTURE_STAGE_WIDTHS) {
    const actual = Math.min(width, nativeWidth ?? width);
    if (announced.has(actual)) continue;
    announced.add(actual);
    candidates.push(`${captureVariantPath(file, width)}${query} ${actual}w`);
  }
  return candidates.join(', ');
}

import { initI18next } from '@/i18n';
import { GhostWord } from '../cosmic/GhostWord';
import type { ApplicationView } from '@/lib/landing/captures';
import {
  CHAPTERS,
  WORLD_CHAPTER_ANCHOR,
  type ChapterConfig,
  type ChapterId,
} from './chapters-data';
import { ChapterSection } from './ChapterSection';
import { ProductScene } from '../demo/ProductScene';
import { ScreenshotsSection } from '../ScreenshotsSection';
import { SecurityDetail } from './SecurityDetail';
import { WorldPlaces } from './WorldPlaces';

/** The chapters shown by a capture of the application; the others take a scene. */
const CHAPTER_CAPTURES: Partial<Record<ChapterId, ApplicationView>> = {
  tools: 'tools',
  act: 'meetings',
  know: 'relations',
  grow: 'knowledge',
  world: 'world',
};

function chapterVisual(chapter: ChapterConfig) {
  const view = CHAPTER_CAPTURES[chapter.id];
  return view ? <ScreenshotsSection view={view} /> : <ProductScene sceneId={chapter.scene} home />;
}

/**
 * Each chapter takes a capture of the application, or a completed frame from
 * the same scenes as the hero: the story and its illustration share one
 * product vocabulary.
 *
 * `ghosts` (used by the cosmos landing, default off):
 * each chapter receives its translated GhostWord with alternating drift.
 */
export async function EditorialChapters({
  lng,
  ghosts = false,
}: {
  lng: string;
  ghosts?: boolean;
}) {
  const { t } = await initI18next(lng);

  return (
    // `features` keeps the historical anchor alive (skip link, external links)
    <div id="features" className="scroll-mt-24">
      {CHAPTERS.map((chapter, i) => (
        <ChapterSection
          key={chapter.id}
          t={t}
          chapter={chapter}
          reverse={i % 2 === 1}
          visual={chapterVisual(chapter)}
          catalogExtra={
            chapter.id === 'control' ? (
              <SecurityDetail t={t} lng={lng} />
            ) : chapter.id === 'world' ? (
              <WorldPlaces t={t} />
            ) : chapter.id === 'connect' ? (
              <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
                {t('landing.chapters.c6.world_note')}{' '}
                <a
                  href={`#${WORLD_CHAPTER_ANCHOR}`}
                  className="rounded font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {t('landing.chapters.c6.world_link')}
                </a>
              </p>
            ) : undefined
          }
          ghost={
            ghosts ? (
              <GhostWord
                wordKey={`landing.cosmos.ghost.${chapter.id}`}
                direction={i % 2 === 0 ? 1 : -1}
              />
            ) : undefined
          }
        />
      ))}
    </div>
  );
}

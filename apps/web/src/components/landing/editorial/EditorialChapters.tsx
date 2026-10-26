import { initI18next } from '@/i18n';
import { GhostWord } from '../cosmic/GhostWord';
import { CHAPTERS, WORLD_CHAPTER_ANCHOR } from './chapters-data';
import { ChapterSection } from './ChapterSection';
import { ProductScene } from '../demo/ProductScene';
import { ScreenshotsSection } from '../ScreenshotsSection';
import { SecurityDetail } from './SecurityDetail';
import { WorldPlaces } from './WorldPlaces';

/**
 * Each chapter takes a completed frame from the same scenes as the hero.
 * The story and its illustration therefore share one product vocabulary.
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
          visual={
            chapter.id === 'act' ? (
              <ScreenshotsSection view="meetings" />
            ) : chapter.id === 'know' ? (
              <ScreenshotsSection view="relations" />
            ) : chapter.id === 'grow' ? (
              <ScreenshotsSection view="knowledge" />
            ) : chapter.id === 'world' ? (
              <ScreenshotsSection view="world" />
            ) : (
              <ProductScene sceneId={chapter.scene} home />
            )
          }
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

import { initI18next } from '@/i18n';
import { GhostWord } from '../cosmic/GhostWord';
import { CHAPTERS } from './chapters-data';
import { ChapterSection } from './ChapterSection';
import { ProductScene } from '../demo/ProductScene';
import { SecurityDetail } from './SecurityDetail';

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
          visual={<ProductScene sceneId={chapter.scene} />}
          catalogExtra={chapter.id === 'control' ? <SecurityDetail t={t} lng={lng} /> : undefined}
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

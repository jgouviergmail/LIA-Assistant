import { initI18next } from '@/i18n';
import { CHAPTERS } from './chapters-data';
import { ChapterSection } from './ChapterSection';
import { SceneBriefing, SceneEdit, SceneRelay } from './scenes';
import { SecurityDetail } from './SecurityDetail';
import { VignetteForge, VignetteOrchestration, VignetteSpark } from './vignettes';

/**
 * The six-chapter narrative replacing the former features wall,
 * how-it-works and security sections. Visuals alternate between decomposed
 * backstage vignettes (chapters 01/03/05) and complementary chat scenes
 * (chapters 02/04/06) — never duplicating the hero's four acts.
 */
export async function EditorialChapters({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);

  const visuals: Record<string, React.ReactNode> = {
    act: <VignetteOrchestration t={t} />,
    know: <SceneBriefing t={t} />,
    anticipate: <VignetteSpark t={t} />,
    control: <SceneEdit t={t} />,
    grow: <VignetteForge t={t} />,
    connect: <SceneRelay t={t} />,
  };

  return (
    // `features` keeps the historical anchor alive (skip link, external links)
    <div id="features" className="scroll-mt-24">
      {CHAPTERS.map((chapter, i) => (
        <ChapterSection
          key={chapter.id}
          t={t}
          chapter={chapter}
          reverse={i % 2 === 1}
          visual={visuals[chapter.id]}
          catalogExtra={chapter.id === 'control' ? <SecurityDetail t={t} lng={lng} /> : undefined}
        />
      ))}
    </div>
  );
}

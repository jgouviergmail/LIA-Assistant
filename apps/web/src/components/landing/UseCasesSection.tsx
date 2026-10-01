import { ArrowDown, ArrowUpRight } from 'lucide-react';
import { initI18next } from '@/i18n';
import { cn } from '@/lib/utils';
import { productScene, PRODUCT_DEMO_KEY } from './demo/scenes';
import { SCENE_TONES } from './demo/scene-tones';
import { CHAPTERS } from './editorial/chapters-data';
import { FadeInOnScroll } from './FadeInOnScroll';

/** The same scenarios as the demo, presented as a visual route into the chapters. */
export async function UseCasesSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);

  return (
    <section
      id="use-cases"
      className="landing-section scroll-mt-24 py-16 sm:py-20"
      aria-labelledby="use-cases-title"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        {/* The intro spans the column its cards span: capped at 48rem it sat on
            two lines above a 1088px grid (measured 2026-10-01 at 1280-1920px). */}
        <div className="mb-8">
          <h2 id="use-cases-title" className="text-3xl font-bold tracking-tight mobile:text-4xl">
            {t('landing.editorial.examples_title')}
          </h2>
          <p className="mt-4 text-pretty leading-relaxed text-muted-foreground">
            {t('landing.editorial.examples_sub')}
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {CHAPTERS.map(chapter => {
            const scene = productScene(chapter.scene);
            const Icon = scene.icon;
            const tone = SCENE_TONES[scene.id];
            const prefix = `${PRODUCT_DEMO_KEY}.scenes.${scene.id}`;
            return (
              <FadeInOnScroll key={scene.id}>
                <a
                  href={`#${chapter.anchor}`}
                  className="group flex h-full flex-col rounded-2xl border border-border bg-card/80 p-5 transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:p-6"
                >
                  <div className="flex items-start gap-3">
                    <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
                    <h3 className="text-lg font-semibold leading-snug">{t(`${prefix}.title`)}</h3>
                    <ArrowUpRight
                      className="ml-auto size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                    {t(`${prefix}.request`)}
                  </p>
                  <div className="mt-auto pt-5" aria-hidden="true">
                    <div className="grid grid-cols-3 gap-1.5">
                      {[1, 2, 3].map(n => (
                        <span
                          key={n}
                          className="flex min-h-10 items-center justify-center rounded-md border border-border/70 bg-background px-2 py-1.5 text-center text-px-11 leading-snug text-muted-foreground"
                        >
                          {t(`${prefix}.source_${n}`)}
                        </span>
                      ))}
                    </div>
                    <div className="flex justify-center py-1.5">
                      <ArrowDown className={cn('size-4', tone.text)} />
                    </div>
                    <div
                      className={cn(
                        'rounded-lg border px-3 py-2.5 text-sm font-medium',
                        tone.border,
                        tone.surface,
                        tone.text
                      )}
                    >
                      {t(`${prefix}.result_title`)}
                    </div>
                  </div>
                  <span className="sr-only">{t('landing.editorial.chapter_scene')}</span>
                </a>
              </FadeInOnScroll>
            );
          })}
        </div>
      </div>
    </section>
  );
}

import { cn } from '@/lib/utils';
import { ChevronDown, Lightbulb } from 'lucide-react';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { SCENE_TONES } from '../demo/scene-tones';
import { CatalogDisclosure } from './CatalogDisclosure';
import { FeatureCatalog, type Translate } from './FeatureCatalog';
import type { ChapterConfig } from './chapters-data';

/** A benefit-led chapter, with a shared product scene and two optional reading depths. */
export function ChapterSection({
  t,
  chapter,
  reverse,
  visual,
  catalogExtra,
  ghost,
}: {
  t: Translate;
  chapter: ChapterConfig;
  /** Visual column on the left (text right) for rhythm on desktop. */
  reverse: boolean;
  visual: React.ReactNode;
  /** Extra catalog content (e.g. the detailed security blocks under c4). */
  catalogExtra?: React.ReactNode;
  /** Cosmos-only decorative background node (GhostWord); absent on `/`. */
  ghost?: React.ReactNode;
}) {
  const k = (suffix: string, options?: Record<string, unknown>) =>
    t(`landing.chapters.${chapter.key}.${suffix}`, options);
  const benefitIndexes = Array.from({ length: chapter.benefits }, (_, i) => i + 1);
  const tone = SCENE_TONES[chapter.scene];

  return (
    <section
      id={chapter.anchor}
      aria-labelledby={`${chapter.anchor}-title`}
      className={cn(
        'landing-section scroll-mt-24 py-16 sm:py-24',
        chapter.tinted && 'border-y border-border/60 bg-card'
      )}
    >
      {ghost}
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        {/* min-w-0 on both grid items: a chip row's or truncated pill's
            intrinsic width must never widen the track past the viewport */}
        <div className="grid items-center gap-8 lg:grid-cols-[1fr_1.1fr] lg:gap-12">
          <FadeInOnScroll className={cn('min-w-0', reverse && 'lg:order-2')}>
            <p className={cn('text-xs font-medium', tone.text)}>
              {t('landing.chapters.eyebrow')} {chapter.num}
            </p>
            <h2
              id={`${chapter.anchor}-title`}
              className="mt-1.5 text-3xl font-bold tracking-tight mobile:text-4xl"
            >
              {k('title')}
            </h2>
            <p className="mt-3 max-w-[48ch] text-muted-foreground">{k('sub')}</p>
            <ul className="mt-6 grid gap-4">
              {benefitIndexes.map(i => (
                <li key={i} className={cn('border-l-2 pl-4 text-sm leading-relaxed', tone.border)}>
                  <strong className="block font-semibold">{k(`b${i}_t`)}</strong>
                  <span className="text-muted-foreground">{k(`b${i}_d`)}</span>
                </li>
              ))}
            </ul>
            <details className="group mt-6 border-t border-border pt-4">
              <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                <Lightbulb className="size-4 shrink-0 text-primary" aria-hidden="true" />
                {t('landing.editorial.mechanism_label')}
                <ChevronDown
                  className="ml-auto size-4 shrink-0 transition-transform group-open:rotate-180"
                  aria-hidden="true"
                />
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{k('mechanism')}</p>
              <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                <strong>{t('landing.editorial.technical_label')}</strong>
                {' : '}
                {k('how')}
              </p>
            </details>
          </FadeInOnScroll>

          <FadeInOnScroll className={cn('min-w-0', reverse && 'lg:order-1')}>
            {visual}
          </FadeInOnScroll>
        </div>

        <CatalogDisclosure
          summary={t('landing.chapters.catalog_label')}
          hint={k('catalog_hint', { count: chapter.catalog.length })}
          anchor={`${chapter.anchor}-detail`}
        >
          <FeatureCatalog t={t} featureKeys={chapter.catalog} />
          {catalogExtra}
        </CatalogDisclosure>
      </div>
    </section>
  );
}

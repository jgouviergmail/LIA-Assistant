import { cn } from '@/lib/utils';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { CatalogDisclosure } from './CatalogDisclosure';
import { FeatureCatalog, type Translate } from './FeatureCatalog';
import { ScrollStage } from './ScrollStage';
import type { ChapterConfig } from './chapters-data';

/**
 * One chapter of the editorial narrative (reading level 1 + its level-2
 * catalog). Signature device: the section title is introduced by a LIA chat
 * bubble carrying the chapter's psyche mood — the page speaks the product's
 * language, in direct continuity with the animated hero.
 */
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
  const k = (suffix: string) => t(`landing.chapters.${chapter.key}.${suffix}`);
  const benefitIndexes = Array.from({ length: chapter.benefits }, (_, i) => i + 1);

  return (
    <section
      id={chapter.anchor}
      aria-labelledby={`${chapter.anchor}-title`}
      className={cn(
        'landing-section scroll-mt-24 py-24',
        chapter.tinted && 'border-y border-border/60 bg-card'
      )}
    >
      {ghost}
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        {/* min-w-0 on both grid items: a chip row's or truncated pill's
            intrinsic width must never widen the track past the viewport */}
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          <FadeInOnScroll className={cn('min-w-0', reverse && 'lg:order-2')}>
            {/* Signature: the chapter opens with LIA's voice */}
            <div className="mb-5 flex items-start gap-2.5" aria-hidden="true">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-card text-base leading-none">
                {chapter.mood}
              </span>
              <span className="rounded-2xl rounded-tl-[5px] border border-border bg-card px-3.5 py-2 text-sm italic text-muted-foreground">
                {k('bubble')}
              </span>
            </div>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-primary">
              {t('landing.chapters.eyebrow')} {chapter.num}
            </p>
            <h2
              id={`${chapter.anchor}-title`}
              className="mt-1.5 text-3xl font-bold tracking-tight mobile:text-4xl"
            >
              {k('title')}
            </h2>
            <p className="mt-3 max-w-[48ch] text-muted-foreground">{k('sub')}</p>
            <ul className="mt-7 space-y-3.5">
              {benefitIndexes.map(i => (
                <li key={i} className="flex items-baseline gap-2.5 text-sm leading-relaxed">
                  <span aria-hidden="true" className="font-bold text-primary">
                    —
                  </span>
                  <span>
                    <strong className="font-semibold">{k(`b${i}_t`)}</strong> {k(`b${i}_d`)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-7 border-t border-dashed border-border pt-3 text-xs text-muted-foreground">
              <strong className="font-semibold">{t('landing.chapters.how_prefix')}</strong>{' '}
              {k('how')}
            </p>
          </FadeInOnScroll>

          <ScrollStage className={cn('min-w-0', reverse && 'lg:order-1')}>
            <div aria-hidden="true">{visual}</div>
          </ScrollStage>
        </div>

        <CatalogDisclosure
          summary={t('landing.chapters.catalog_label')}
          hint={k('catalog_hint')}
          anchor={`${chapter.anchor}-detail`}
        >
          <FeatureCatalog t={t} featureKeys={chapter.catalog} />
          {catalogExtra}
        </CatalogDisclosure>
      </div>
    </section>
  );
}

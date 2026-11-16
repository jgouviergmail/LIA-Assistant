import { initI18next } from '@/i18n';
import { cn } from '@/lib/utils';
import { AnimatedCounter } from '../AnimatedCounter';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { brickCountFloor } from '../comparison/brick-floor';
import { ContenderMark } from '../comparison/ContenderMark';
import type { ContenderId } from '../comparison/comparison-data';

/**
 * Where LIA stands, right under the hero, one tile under the other (owner,
 * 2026-11-15): the market split in two, each world shown by the marks of the
 * products the text names, then the thesis in the cosmos gradient with its
 * figure. The figure is the living map's brick count floored to ten
 * (`brickCountFloor`), so « 60+ » stays true without an edit; it counts up once
 * in view, never in a loop.
 */
export async function PositioningSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  const floor = brickCountFloor();

  return (
    <section
      id="positioning"
      aria-labelledby="positioning-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card/70 py-12 sm:py-20"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          {/* Centred under the hero's centred tagline (owner, 2026-11-15). */}
          <h2
            id="positioning-title"
            className="text-center text-3xl font-bold tracking-tight text-foreground mobile:text-4xl"
          >
            {t('landing.positioning.title')}
          </h2>
          <div className="mt-8 space-y-5">
            <div className="overflow-hidden rounded-2xl border border-border/70 bg-background/80 shadow-sm">
              <MarketBand marks={['openclaw', 'hermes']} text={t('landing.positioning.market_agents')} />
              <MarketBand marks={['muse']} text={t('landing.positioning.market_cloud')} divided />
            </div>

            <div className="rounded-2xl p-px shadow-[0_18px_48px_-22px_var(--color-primary)] [background:var(--cosmos-grad)]">
              <div className="grid gap-5 rounded-[calc(1rem-1px)] bg-background/95 p-5 sm:p-7 md:grid-cols-[auto_minmax(0,1fr)] md:items-center md:gap-8">
                <div className="text-center md:border-r md:border-border/70 md:pr-8 md:text-left">
                  <p className="bg-clip-text text-5xl font-extrabold leading-none tracking-tight text-transparent [background-image:var(--cosmos-grad)] sm:text-6xl">
                    <AnimatedCounter target={floor} suffix="+" locale={lng} />
                  </p>
                  <p className="mt-2 text-sm font-medium text-muted-foreground">
                    {t('landing.positioning.stat_label')}
                  </p>
                </div>
                <div className="space-y-3">
                  <p className="text-lg font-semibold tracking-tight text-foreground">
                    {t('landing.positioning.thesis_title')}
                  </p>
                  <p className="leading-7 text-muted-foreground">
                    {t('landing.positioning.thesis_body', { count: floor })}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}

/** One side of the split market: the marks of the products it names, then its words. */
function MarketBand({
  marks,
  text,
  divided = false,
}: {
  marks: readonly ContenderId[];
  text: string;
  divided?: boolean;
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:gap-6 sm:p-6',
        divided && 'border-t border-border/70'
      )}
    >
      <div className="flex shrink-0 gap-2 sm:w-24">
        {marks.map(id => (
          <ContenderMark key={id} id={id} size="lg" />
        ))}
      </div>
      <p className="leading-7 text-muted-foreground">{text}</p>
    </div>
  );
}

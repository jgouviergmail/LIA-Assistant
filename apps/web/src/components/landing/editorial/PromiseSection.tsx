import { Compass, Network, ShieldCheck } from 'lucide-react';
import { initI18next } from '@/i18n';
import { FadeInOnScroll } from '../FadeInOnScroll';

const PROMISES = [
  { key: 'ecosystem', icon: Network },
  { key: 'trust', icon: ShieldCheck },
  { key: 'freedom', icon: Compass },
] as const;

/** The fuller introduction follows the hero, where it can be read at an easy pace. */
export async function PromiseSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);

  return (
    <section
      aria-labelledby="landing-promise-title"
      className="landing-section relative isolate overflow-hidden border-y border-border/60 bg-card/70 py-16 sm:py-20"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-36 -top-56 size-[30rem] rounded-full bg-primary/5 blur-3xl"
      />
      <div className="relative mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              {t('landing.promise.eyebrow')}
            </p>
            <h2
              id="landing-promise-title"
              className="mt-4 text-3xl font-bold tracking-tight text-foreground sm:text-4xl"
            >
              {t('landing.promise.title')}
            </h2>
            <p className="mt-5 max-w-[68ch] text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
              {t('landing.promise.lead')}
            </p>
          </div>
        </FadeInOnScroll>

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {PROMISES.map(({ key, icon: Icon }, index) => (
            <FadeInOnScroll key={key}>
              <article className="h-full rounded-2xl border border-border/70 bg-background/80 p-6 shadow-sm sm:p-7">
                <div className="flex items-center justify-between">
                  <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Icon className="size-5" aria-hidden="true" />
                  </span>
                  <span className="text-xs font-semibold tabular-nums tracking-widest text-muted-foreground">
                    0{index + 1}
                  </span>
                </div>
                <h3 className="mt-6 text-lg font-semibold tracking-tight text-foreground">
                  {t(`landing.promise.${key}.title`)}
                </h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  {t(`landing.promise.${key}.body`)}
                </p>
              </article>
            </FadeInOnScroll>
          ))}
        </div>
      </div>
    </section>
  );
}

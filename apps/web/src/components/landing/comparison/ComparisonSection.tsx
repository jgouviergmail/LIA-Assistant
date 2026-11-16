import { initI18next } from '@/i18n';
import type { Language } from '@/i18n/settings';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { ComparisonExplorer } from './ComparisonExplorer';
import { formatSourcesReadOn } from './comparison-data';

/** The comparison under its own heading: LIA facing one contender at a time. */
export async function ComparisonSection({ lng }: { lng: Language }) {
  const { t } = await initI18next(lng);

  return (
    <section
      id="comparison"
      aria-labelledby="comparison-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card/70 py-12 sm:py-20"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <h2
            id="comparison-title"
            className="text-3xl font-bold tracking-tight text-foreground mobile:text-4xl"
          >
            {t('landing.comparison.title')}
          </h2>
          <p className="mt-4 mb-8 leading-7 text-muted-foreground">
            {t('landing.comparison.lede')}
          </p>
        </FadeInOnScroll>
        <ComparisonExplorer readOn={formatSourcesReadOn(lng)} />
      </div>
    </section>
  );
}

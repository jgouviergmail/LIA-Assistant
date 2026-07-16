import { initI18next } from '@/i18n';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { CatalogDisclosure } from './CatalogDisclosure';
import { FeatureCatalog } from './FeatureCatalog';
import { BASICS_CATALOG, BASICS_CHIPS } from './chapters-data';

/**
 * "And everything else, obviously." — the commodity features condensed into
 * one confident band AFTER the differentiation chapters, so the post-hero
 * attention peak is never spent on table stakes. The former commodity cards
 * survive verbatim inside the band's own catalog (zero information loss).
 */
export async function BasicsBand({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);

  return (
    <section
      id="basics"
      aria-labelledby="basics-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card py-16"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <h2 id="basics-title" className="text-2xl font-bold tracking-tight">
            {t('landing.basics.title')}
          </h2>
          <p className="mt-2 max-w-[68ch] text-sm text-muted-foreground">
            {t('landing.basics.sub')}
          </p>
          <ul className="mt-6 flex list-none flex-wrap gap-2">
            {BASICS_CHIPS.map(({ emoji, key }) => (
              <li
                key={key}
                className="rounded-full border border-border bg-background px-3.5 py-1.5 text-xs"
              >
                <span aria-hidden="true">{emoji}</span> {t(`landing.basics.${key}`)}
              </li>
            ))}
          </ul>
        </FadeInOnScroll>
        <CatalogDisclosure
          summary={t('landing.basics.detail_label')}
          hint={t('landing.basics.detail_hint')}
          anchor="basics-detail"
        >
          <FeatureCatalog t={t} featureKeys={BASICS_CATALOG} />
        </CatalogDisclosure>
      </div>
    </section>
  );
}

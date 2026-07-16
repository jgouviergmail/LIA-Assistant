import { FEATURE_ICONS } from './chapters-data';

/** Server-side translate function shape shared by the editorial sections. */
export type Translate = (key: string) => string;

/**
 * The detailed feature cards (reading level 2), reusing the existing
 * `landing.features.<key>.{title,description}` copy — already translated in
 * all 6 locales. Rendered inside a CatalogDisclosure; stays in the DOM while
 * collapsed so every description remains crawlable.
 */
export function FeatureCatalog({ t, featureKeys }: { t: Translate; featureKeys: readonly string[] }) {
  return (
    <ul className="grid list-none grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {featureKeys.map(key => {
        const Icon = FEATURE_ICONS[key];
        return (
          <li
            key={key}
            className="rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/30"
          >
            <h4 className="flex items-center gap-2 text-sm font-semibold">
              {Icon && <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />}
              {t(`landing.features.${key}.title`)}
            </h4>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              {t(`landing.features.${key}.description`)}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

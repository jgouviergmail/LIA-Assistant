import { FeatureExplorer } from './FeatureExplorer';
import { FEATURE_SCENES } from './FeatureScenes';

/**
 * Server-side translate function shape shared by the editorial sections.
 * `options` carries interpolation values (a derived `count`, never a number
 * typed into the copy).
 */
export type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * Translate on the server, then pass serializable copy to the explorer.
 * Every complete description remains in the DOM, including inactive panels.
 * The chapter's editorial order is also the explorer's reading order.
 */
export function FeatureCatalog({
  t,
  featureKeys,
}: {
  t: Translate;
  featureKeys: readonly string[];
}) {
  return (
    <FeatureExplorer
      items={featureKeys.map((key, index) => ({
        id: key,
        title: t(`landing.features.${key}.title`),
        description: t(`landing.features.${key}.description`),
        sceneLabel: t(`landing.catalog_explorer.scenes.${FEATURE_SCENES[key]}`),
        positionLabel: t('landing.catalog_explorer.position', {
          current: index + 1,
          total: featureKeys.length,
        }),
      }))}
      labels={{
        browse: t('landing.catalog_explorer.browse'),
        hint: t('landing.catalog_explorer.hint'),
        previous: t('landing.catalog_explorer.previous'),
        next: t('landing.catalog_explorer.next'),
      }}
    />
  );
}

import type { ZoneId } from '@/features/world/types';
import type { Translate } from './FeatureCatalog';

/** Authored places; labels reuse the native directory in every language. */
export const WORLD_PLACE_IDS = [
  'arrival',
  'meeting',
  'multimedia',
  'phone',
  'memory',
  'cafeteria',
  'engineering',
  'gym',
  'divination',
  'library',
  'restroom',
  'garden',
  'terrace',
  'home',
] as const satisfies readonly ZoneId[];

export function WorldPlaces({ t }: { t: Translate }) {
  return (
    <div className="mt-8 border-t border-border pt-6">
      <h3 className="text-lg font-semibold">{t('landing.world_places.title')}</h3>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
        {t('landing.world_places.intro')}
      </p>
      <dl className="mt-6 grid gap-x-8 sm:grid-cols-2">
        {WORLD_PLACE_IDS.map(id => (
          <div key={id} className="border-t border-border py-4">
            <dt className="font-medium">{t(`world.zones.${id}`)}</dt>
            <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {t(`landing.world_places.places.${id}`)}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
        {t('landing.world_places.note')}
      </p>
    </div>
  );
}

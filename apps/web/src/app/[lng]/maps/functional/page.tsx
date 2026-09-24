import { type Metadata } from 'next';

import { FunctionalMap } from '@/components/maps/FunctionalMap';
import { MapsHero } from '@/components/maps/MapsHero';
import { MapsShell } from '@/components/maps/MapsShell';
import { MapsTabs } from '@/components/maps/MapsTabs';
import { initI18next, validateLanguage } from '@/i18n';
import { mapsData } from '@/lib/maps/data';
import { mapsFormat } from '@/lib/maps/format';
import { MAPS_HOME_PATH, MAP_PAGE_PATHS } from '@/lib/maps/links';
import { mapsMetadata, siteUrl } from '@/lib/maps/metadata';
import { buildBrickMap } from '@/lib/maps/model';

/**
 * `/maps/functional` — what LIA does, brick by brick: the constellation of the
 * functional bricks, their families, and the journeys that cross them.
 */

interface PageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const map = buildBrickMap(mapsData(lng), 'functional');
  return mapsMetadata(lng, MAP_PAGE_PATHS.functional, t('maps.meta.functional_title'), map.lede);
}

export default async function FunctionalMapPage({ params }: PageProps) {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const map = buildBrickMap(mapsData(lng), 'functional');
  const format = mapsFormat(lng);
  const n = format.number;

  return (
    <MapsShell
      lng={lng}
      breadcrumb={[
        { name: 'LIA', url: siteUrl('/', lng) },
        { name: t('maps.section'), url: siteUrl(MAPS_HOME_PATH, lng) },
        { name: t('maps.pages.functional'), url: siteUrl(MAP_PAGE_PATHS.functional, lng) },
      ]}
    >
      <MapsTabs lng={lng} current="functional" t={t} />
      <MapsHero
        eyebrow={t('maps.functional.eyebrow')}
        title={t('maps.functional.title')}
        lede={map.lede}
        stats={[
          {
            value: n(map.bricks.length),
            label: t('maps.labels.functional_bricks', { count: map.bricks.length }),
          },
          {
            value: n(map.families.length),
            label: t('maps.labels.families', { count: map.families.length }),
          },
          {
            value: n(map.flows.length),
            label: t('maps.labels.flows', { count: map.flows.length }),
          },
          {
            value: n(map.facts.domains),
            label: t('maps.labels.domains_code', { count: map.facts.domains }),
          },
          {
            value: n(map.facts.decisions),
            label: t('maps.labels.linked_decisions', { count: map.facts.decisions }),
          },
        ]}
        stamp={{
          version: t('maps.stamp.version', { version: map.facts.version }),
          date: format.day(map.facts.releaseDate),
          note: t('maps.stamp.note'),
        }}
      />
      <FunctionalMap map={map} lng={lng} />
    </MapsShell>
  );
}

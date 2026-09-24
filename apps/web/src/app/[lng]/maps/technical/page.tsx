import { type Metadata } from 'next';

import { MapsHero } from '@/components/maps/MapsHero';
import { MapsShell } from '@/components/maps/MapsShell';
import { MapsTabs } from '@/components/maps/MapsTabs';
import { TechnicalMap } from '@/components/maps/TechnicalMap';
import { initI18next, validateLanguage } from '@/i18n';
import { mapsData } from '@/lib/maps/data';
import { mapsFormat } from '@/lib/maps/format';
import { MAPS_HOME_PATH, MAP_PAGE_PATHS } from '@/lib/maps/links';
import { mapsMetadata, siteUrl } from '@/lib/maps/metadata';
import { buildBrickMap } from '@/lib/maps/model';

/**
 * `/maps/technical` — how LIA is built, layer by layer: the technical bricks,
 * their technologies, where they live in the repository, and the path a
 * request takes through them.
 */

interface PageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const map = buildBrickMap(mapsData(lng), 'technical');
  return mapsMetadata(lng, MAP_PAGE_PATHS.technical, t('maps.meta.technical_title'), map.lede);
}

export default async function TechnicalMapPage({ params }: PageProps) {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const map = buildBrickMap(mapsData(lng), 'technical');
  const format = mapsFormat(lng);
  const n = format.number;

  return (
    <MapsShell
      lng={lng}
      breadcrumb={[
        { name: 'LIA', url: siteUrl('/', lng) },
        { name: t('maps.section'), url: siteUrl(MAPS_HOME_PATH, lng) },
        { name: t('maps.pages.technical'), url: siteUrl(MAP_PAGE_PATHS.technical, lng) },
      ]}
    >
      <MapsTabs lng={lng} current="technical" t={t} />
      <MapsHero
        eyebrow={t('maps.technical.eyebrow')}
        title={t('maps.technical.title')}
        lede={map.lede}
        stats={[
          {
            value: n(map.bricks.length),
            label: t('maps.labels.technical_bricks', { count: map.bricks.length }),
          },
          {
            value: n(map.families.length),
            label: t('maps.labels.layers', { count: map.families.length }),
          },
          {
            value: n(map.flows.length),
            label: t('maps.labels.flows', { count: map.flows.length }),
          },
          { value: n(map.facts.infra), label: t('maps.labels.infra', { count: map.facts.infra }) },
          {
            value: n(map.facts.domains),
            label: t('maps.labels.domains_served', { count: map.facts.domains }),
          },
        ]}
        stamp={{
          version: t('maps.stamp.version', { version: map.facts.version }),
          date: format.day(map.facts.releaseDate),
          note: t('maps.stamp.note'),
        }}
      />
      <TechnicalMap map={map} lng={lng} />
    </MapsShell>
  );
}

import { type Metadata } from 'next';

import { HistoryMap } from '@/components/maps/HistoryMap';
import { MapsHero } from '@/components/maps/MapsHero';
import { MapsShell } from '@/components/maps/MapsShell';
import { MapsTabs } from '@/components/maps/MapsTabs';
import { initI18next, validateLanguage } from '@/i18n';
import { mapsData } from '@/lib/maps/data';
import { mapsFormat } from '@/lib/maps/format';
import { MAPS_HOME_PATH, MAP_PAGE_PATHS } from '@/lib/maps/links';
import { mapsMetadata, siteUrl } from '@/lib/maps/metadata';
import { buildHistory } from '@/lib/maps/model';
import { monthRange } from '@/lib/maps/timeline';

/**
 * `/maps/history` — every architecture decision of LIA, told in a few plain
 * sentences, dated, themed and linked to the bricks it shaped.
 */

interface PageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const view = buildHistory(mapsData(lng));
  return mapsMetadata(lng, MAP_PAGE_PATHS.history, t('maps.meta.history_title'), view.lede);
}

export default async function HistoryMapPage({ params }: PageProps) {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const view = buildHistory(mapsData(lng));
  const format = mapsFormat(lng);
  const n = format.number;
  const months = monthRange(view.decisions);
  const span = months.length
    ? `${format.month(months[0])} → ${format.month(months[months.length - 1])}`
    : '';

  return (
    <MapsShell
      lng={lng}
      breadcrumb={[
        { name: 'LIA', url: siteUrl('/', lng) },
        { name: t('maps.section'), url: siteUrl(MAPS_HOME_PATH, lng) },
        { name: t('maps.pages.history'), url: siteUrl(MAP_PAGE_PATHS.history, lng) },
      ]}
    >
      <MapsTabs lng={lng} current="history" t={t} />
      <MapsHero
        eyebrow={t('maps.history.eyebrow')}
        title={t('maps.history.title')}
        lede={view.lede}
        stats={[
          {
            value: n(view.decisions.length),
            label: t('maps.labels.decisions', { count: view.decisions.length }),
          },
          {
            value: n(view.themes.length),
            label: t('maps.labels.themes', { count: view.themes.length }),
          },
          {
            value: n(view.facts.releases),
            label: t('maps.labels.releases', { count: view.facts.releases }),
          },
          {
            value: n(view.eras.length),
            label: t('maps.labels.chapters', { count: view.eras.length }),
          },
          {
            value: t('maps.stats.months', { count: months.length, value: n(months.length) }),
            label: span,
          },
        ]}
        stamp={{
          version: t('maps.stamp.version', { version: view.facts.version }),
          date: format.day(view.facts.releaseDate),
          note: t('maps.stamp.note'),
        }}
      />
      <HistoryMap view={view} lng={lng} />
    </MapsShell>
  );
}

import { type Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, History, LayoutGrid, Network, ShieldCheck } from 'lucide-react';

import { MapsHero } from '@/components/maps/MapsHero';
import { MapsShell } from '@/components/maps/MapsShell';
import { MapsTabs } from '@/components/maps/MapsTabs';
import { initI18next, validateLanguage } from '@/i18n';
import { mapsData } from '@/lib/maps/data';
import { mapsFormat } from '@/lib/maps/format';
import { MAPS_HOME_PATH, mapPageHref } from '@/lib/maps/links';
import { mapsMetadata, siteUrl } from '@/lib/maps/metadata';
import { buildSummary } from '@/lib/maps/model';
import type { MapPage, Tone } from '@/lib/maps/types';

/**
 * `/maps` — the home of the "Maps" section: the three living maps of LIA, what
 * each one answers, and the counts it rests on. A reading page of the public
 * site (cosmos calm scope), declared in `lib/public-pages.ts`.
 */

interface MapsPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: MapsPageProps): Promise<Metadata> {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  return mapsMetadata(
    lng,
    MAPS_HOME_PATH,
    t('maps.meta.hub_title'),
    t('maps.meta.hub_description')
  );
}

const CARDS: ReadonlyArray<{ page: MapPage; icon: typeof LayoutGrid; tone: Tone }> = [
  { page: 'functional', icon: LayoutGrid, tone: 'blue' },
  { page: 'technical', icon: Network, tone: 'violet' },
  { page: 'history', icon: History, tone: 'cyan' },
];

export default async function MapsPage({ params }: MapsPageProps) {
  const lng = validateLanguage((await params).lng);
  const { t } = await initI18next(lng);
  const summary = buildSummary(mapsData(lng));
  const format = mapsFormat(lng);
  const n = format.number;

  const cardStats: Record<MapPage, string[]> = {
    functional: [
      t('maps.stats.bricks', {
        count: summary.functional.bricks,
        value: n(summary.functional.bricks),
      }),
      t('maps.stats.families', {
        count: summary.functional.families,
        value: n(summary.functional.families),
      }),
      t('maps.stats.flows', {
        count: summary.functional.flows,
        value: n(summary.functional.flows),
      }),
    ],
    technical: [
      t('maps.stats.bricks', {
        count: summary.technical.bricks,
        value: n(summary.technical.bricks),
      }),
      t('maps.stats.layers', {
        count: summary.technical.layers,
        value: n(summary.technical.layers),
      }),
      t('maps.stats.flows', { count: summary.technical.flows, value: n(summary.technical.flows) }),
    ],
    history: [
      t('maps.stats.decisions', {
        count: summary.history.decisions,
        value: n(summary.history.decisions),
      }),
      t('maps.stats.themes', { count: summary.history.themes, value: n(summary.history.themes) }),
      t('maps.stats.chapters', { count: summary.history.eras, value: n(summary.history.eras) }),
    ],
  };

  return (
    <MapsShell
      lng={lng}
      breadcrumb={[
        { name: 'LIA', url: siteUrl('/', lng) },
        { name: t('maps.section'), url: siteUrl(MAPS_HOME_PATH, lng) },
      ]}
    >
      <MapsTabs lng={lng} current="home" t={t} />
      <MapsHero
        eyebrow={t('maps.hub.eyebrow')}
        title={t('maps.hub.title')}
        lede={t('maps.hub.lede')}
        stats={[
          {
            value: n(summary.functional.bricks + summary.technical.bricks),
            label: t('maps.labels.bricks_both', {
              count: summary.functional.bricks + summary.technical.bricks,
            }),
          },
          {
            value: n(summary.facts.decisions),
            label: t('maps.labels.decisions', { count: summary.facts.decisions }),
          },
          {
            value: n(summary.facts.domains),
            label: t('maps.labels.domains', { count: summary.facts.domains }),
          },
          {
            value: n(summary.facts.releases),
            label: t('maps.labels.releases', { count: summary.facts.releases }),
          },
        ]}
        stamp={{
          version: t('maps.stamp.version', { version: summary.facts.version }),
          date: format.day(summary.facts.releaseDate),
          note: t('maps.stamp.note'),
        }}
      />
      <section className="lm-section" aria-labelledby="lm-hub-title">
        <h2 id="lm-hub-title" className="sr-only">
          {t('maps.tabs_label')}
        </h2>
        <ul className="lm-hub-grid">
          {CARDS.map(({ page, icon: Icon, tone }) => (
            <li key={page}>
              <article className="lm-hub-card" data-tone={tone}>
                <span className="lm-badge-ic">
                  <Icon aria-hidden="true" width={20} height={20} />
                </span>
                <h3>
                  <Link className="lm-hub-link" href={mapPageHref(page, lng)}>
                    {t(`maps.pages.${page}`)}
                  </Link>
                </h3>
                <p>{summary.lede[page]}</p>
                <ul className="lm-hub-stats">
                  {cardStats[page].map(stat => (
                    <li key={stat}>{stat}</li>
                  ))}
                </ul>
                <span className="lm-hub-cta" aria-hidden="true">
                  {t('maps.hub.open')}
                  <ArrowRight width={16} height={16} />
                </span>
              </article>
            </li>
          ))}
        </ul>
        <p className="lm-hub-note">
          <ShieldCheck aria-hidden="true" width={18} height={18} className="lm-ic" />
          {t('maps.hub.note')}
        </p>
      </section>
    </MapsShell>
  );
}

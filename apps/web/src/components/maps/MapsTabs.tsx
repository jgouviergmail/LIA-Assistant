import Link from 'next/link';
import { History, LayoutGrid, Map as MapGlyph, Network } from 'lucide-react';

import type { Language } from '@/i18n/settings';
import { MAPS_HOME_PATH, mapPageHref } from '@/lib/maps/links';
import { MAP_PAGES, type MapPage } from '@/lib/maps/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

const PAGE_ICONS: Readonly<Record<MapPage, typeof LayoutGrid>> = {
  functional: LayoutGrid,
  technical: Network,
  history: History,
};

/**
 * The section's own navigation: its home and the three maps, the current one
 * stated with `aria-current` — a reader moves from one map to the next without
 * going back through the site's header. Synchronous: the page hands it the
 * translator it already holds.
 */
export function MapsTabs({
  lng,
  current,
  t,
}: {
  lng: Language;
  current: MapPage | 'home';
  t: (key: string) => string;
}) {
  return (
    <nav aria-label={t('maps.tabs_label')} className="lm-tabs">
      <Link
        href={buildLocalizedPath(MAPS_HOME_PATH, lng)}
        aria-current={current === 'home' ? 'page' : undefined}
      >
        <MapGlyph aria-hidden="true" width={16} height={16} />
        {t('maps.section')}
      </Link>
      {MAP_PAGES.map(page => {
        const Icon = PAGE_ICONS[page];
        return (
          <Link
            key={page}
            href={mapPageHref(page, lng)}
            aria-current={current === page ? 'page' : undefined}
          >
            <Icon aria-hidden="true" width={16} height={16} />
            {t(`maps.pages.${page}`)}
          </Link>
        );
      })}
    </nav>
  );
}

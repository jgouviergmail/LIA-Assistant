'use client';

/**
 * The capability map, in whichever form the reader's device and preferences
 * call for.
 *
 * A wide screen gets the chart; a phone gets the list. Not a fallback — the
 * same data, the same order, the same destinations. What a 340-pixel square
 * cannot hold is thirteen absolutely-positioned labels, which is a pile rather
 * than a map.
 *
 * **Reduced motion keeps the CHART and loses only the movement.** Asking for
 * stillness is not asking for less information, and the map's meaning was
 * never in its rotation — the figure, the magnitudes and the states are all
 * still there, simply at rest.
 *
 * The choice is made with `useMediaQuery`, which answers `false` during SSR
 * and the first paint: the LIST is therefore what the server renders, and a
 * desktop reader gets the constellation once the client knows the viewport. A
 * map that flashed as a constellation and collapsed into a list would be worse
 * than one that arrives as a list and blooms.
 */

import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { CapabilityConstellation } from './CapabilityConstellation';
import { CapabilityList } from './CapabilityList';
import { useCapabilities } from '@/hooks/useCapabilities';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { sectionOfCapability } from '@/lib/capability-sections';
import { settingsSectionHref } from '@/lib/settings-sections';

export function CapabilityMapView({ lng }: { lng: string }) {
  const { t } = useTranslation();
  const { nodes, live, total, firstLoad, error } = useCapabilities();
  const wide = useMediaQuery('(min-width: 1024px)');
  const stillness = useMediaQuery('(prefers-reduced-motion: reduce)');

  if (firstLoad) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner className="h-6 w-6" />
      </div>
    );
  }

  // Checked BEFORE emptiness: "no capability" on a failed read would tell the
  // reader their assistant can do nothing, which is almost certainly false.
  if (error && !nodes) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('capabilities.error')}
      </p>
    );
  }

  if (!nodes?.length) {
    return <p className="text-sm italic text-muted-foreground">{t('capabilities.empty')}</p>;
  }

  const hrefOf = (key: string) => {
    // A capability with no section of its own (document generation: nothing to
    // configure per account) points at the settings root rather than nowhere —
    // a dead link is worse than a general one.
    const token = sectionOfCapability(key);
    return token ? settingsSectionHref(lng, token) : `/${lng}/dashboard/settings`;
  };

  return wide ? (
    <CapabilityConstellation
      nodes={nodes}
      live={live}
      total={total}
      hrefOf={hrefOf}
      reducedMotion={stillness}
    />
  ) : (
    <CapabilityList nodes={nodes} live={live} total={total} hrefOf={hrefOf} />
  );
}

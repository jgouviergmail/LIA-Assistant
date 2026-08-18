'use client';

/**
 * SettingsPane — mounts the ONE selected section of the master-detail shell.
 *
 * The section renders exactly as it always has (same component, same
 * `SettingsSection` chokepoint, which is now open by construction) — the pane
 * wraps it in the same `FeatureErrorBoundary` the accordion page used, and
 * keeps the `CatalogueInvalidationProvider` around the admin pricing/config
 * family.
 *
 * ## The honest-absence contract
 *
 * A minority of sections render nothing under their own conditions (no MFA on
 * the instance, no call ever placed, a request still in flight…). Nothing
 * here can tell those cases apart, so the pane polls for the section's anchor
 * and, past the same deadline the accordion page used for its toast, shows an
 * inline empty state that words the OBSERVATION ("not showing here") — and
 * keeps looking, so a section that answers late replaces the message instead
 * of never appearing.
 */

import * as React from 'react';
import { ChevronLeft } from 'lucide-react';

import { FeatureErrorBoundary } from '@/components/errors';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { CatalogueInvalidationProvider } from '@/lib/catalogue-invalidation-context';
import {
  isSectionAvailable,
  SETTINGS_SEARCH_META,
  type SettingsSearchAvailability,
} from '@/lib/settings-search';
import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import { SETTINGS_SECTIONS, type SettingsSectionToken } from '@/lib/settings-sections';

import { SETTINGS_SECTION_REGISTRY } from './settings-section-registry';

/**
 * First look, poll cadence, and how long before absence is worth mentioning.
 * Same values the accordion page used for its reveal-then-toast flow: the
 * deadline is a courtesy, not a verdict — see the module doc.
 */
export const SECTION_FIRST_LOOK_MS = 150;
export const SECTION_POLL_MS = 120;
export const SECTION_SETTLE_DEADLINE_MS = 5000;

export interface SettingsPaneProps {
  lng: Language;
  token: SettingsSectionToken;
  /** Resolved flags for this user and instance — same object the search uses. */
  availability: SettingsSearchAvailability;
  /** Back to the overview (and to the rail, on phones). */
  onBack: () => void;
  /**
   * Increment to move focus onto the section once it settles — the one path
   * that may steal focus is a pick the reader just made in the search field.
   * A deep link or an OAuth return leaves focus alone (0 = never focus).
   */
  focusRequest?: number;
}

export function SettingsPane({
  lng,
  token,
  availability,
  onBack,
  focusRequest = 0,
}: SettingsPaneProps) {
  const { t } = useTranslation(lng);
  const [settled, setSettled] = React.useState<'pending' | 'present' | 'absent'>('pending');
  /**
   * Highest `focusRequest` already honoured. The counter is a ratchet: a
   * search pick increments it and the pane focuses ONCE; a later selection
   * re-runs the settling effect with the same number, and focusing again
   * would yank the caret off the rail button the reader just clicked.
   */
  const focusHonoredRef = React.useRef(0);

  const { accordionValue } = SETTINGS_SECTIONS[token];
  const meta = SETTINGS_SEARCH_META[token];
  const entry = SETTINGS_SECTION_REGISTRY[token];
  const Icon = SETTINGS_SECTION_ICONS[token];
  // A decidable gate that says no (an admin token for a regular account, the
  // debug panel without its grant) means the section must not MOUNT at all —
  // mounting it would fire requests the backend rejects. The poll then finds
  // no anchor and reports honest absence; if the gate flips (a flag lands
  // from `/config`), the section mounts on the next render and the poll
  // replaces the message.
  const mountable = isSectionAvailable(meta.gate, availability);

  React.useEffect(() => {
    setSettled('pending');
    const startedAt = Date.now();
    let timer = 0;

    const look = () => {
      const node = document.getElementById(`settings-section-${accordionValue}`);
      if (node) {
        setSettled('present');
        if (focusRequest > focusHonoredRef.current) {
          focusHonoredRef.current = focusRequest;
          node.focus({ preventScroll: true });
        }
        return;
      }
      if (Date.now() - startedAt >= SECTION_SETTLE_DEADLINE_MS) setSettled('absent');
      timer = window.setTimeout(look, SECTION_POLL_MS);
    };

    timer = window.setTimeout(look, SECTION_FIRST_LOOK_MS);
    return () => window.clearTimeout(timer);
  }, [accordionValue, focusRequest]);

  const section = entry.feature ? (
    <FeatureErrorBoundary feature={entry.feature}>{entry.render(lng)}</FeatureErrorBoundary>
  ) : (
    entry.render(lng)
  );

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" className="-ml-2 lg:hidden" onClick={onBack}>
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        {t('settings.shell.back')}
      </Button>

      {settled === 'absent' && (
        <EmptyState
          variant="page"
          icon={Icon}
          title={t(meta.titleKey)}
          description={t('settings.search.unavailable', { section: t(meta.titleKey) })}
          action={{ label: t('settings.shell.browse_all'), onClick: onBack }}
        />
      )}

      {mountable && <CatalogueInvalidationProvider>{section}</CatalogueInvalidationProvider>}
    </div>
  );
}

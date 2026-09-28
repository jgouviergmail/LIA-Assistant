'use client';

/**
 * The dashboard's logo menu with the header's actions (below `lg`).
 *
 * On a phone the header has no width for its action controls (ADR-259,
 * measured), so each one the instance offers becomes an entry of the logo
 * menu, in the order the header shows them: the meeting recorder, then the
 * radio (ADR-324). The layout is rendered ABOVE the recorder's provider, so the
 * hooks that read it run here, inside it.
 */

import { useMeetingRecorderMenuAction } from '@/components/meetings/MeetingRecorderControl';
import { useRadioMenuAction } from '@/components/radio/RadioControl';
import type { Language } from '@/i18n/settings';

import { MobileNavMenu, type MobileNavAction, type MobileNavMenuProps } from './MobileNavMenu';

type DashboardMobileNavMenuProps = Omit<MobileNavMenuProps, 'actions' | 'live'> & {
  lng: Language;
  /** Whether the instance offers the radio now (`radioAvailable`). */
  radioEnabled: boolean;
};

export function DashboardMobileNavMenu({
  lng,
  radioEnabled,
  ...props
}: DashboardMobileNavMenuProps) {
  const recorder = useMeetingRecorderMenuAction(lng);
  const radio = useRadioMenuAction(lng, radioEnabled);
  const actions = [recorder?.action, radio].filter(
    (action): action is MobileNavAction => action != null
  );
  return <MobileNavMenu {...props} actions={actions} live={recorder?.live ?? undefined} />;
}

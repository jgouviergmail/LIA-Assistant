'use client';

import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import { SettingsPaneFrame, type SettingsPaneProps } from './SettingsPaneFrame';

export type { SettingsPaneProps } from './SettingsPaneFrame';
export {
  SECTION_FIRST_LOOK_MS,
  SECTION_POLL_MS,
  SECTION_SETTLE_DEADLINE_MS,
} from './SettingsPaneFrame';

/** The ordinary settings shell keeps its section-specific icon catalogue. */
export function SettingsPane(props: SettingsPaneProps) {
  return <SettingsPaneFrame {...props} icon={SETTINGS_SECTION_ICONS[props.token]} />;
}

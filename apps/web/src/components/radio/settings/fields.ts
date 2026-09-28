/**
 * What every block of the radio's settings receives: the published options,
 * the listener's current settings, and the one way to change them.
 */
import type { RadioOptions, RadioPreferences } from '@/lib/radio/types';
import type { BaseSettingsProps } from '@/types/settings';

export interface RadioFieldsProps {
  lng: BaseSettingsProps['lng'];
  options: RadioOptions;
  preferences: RadioPreferences;
  /** Saves the whole new settings (optimistic, in order). */
  onChange: (next: RadioPreferences) => void;
}

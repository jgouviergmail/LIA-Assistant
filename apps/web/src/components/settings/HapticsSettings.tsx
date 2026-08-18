'use client';

import { Vibrate } from 'lucide-react';
import { useSyncExternalStore } from 'react';

import { Label } from '@/components/ui/label';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import {
  areHapticsEnabled,
  isHapticsSupported,
  setHapticsEnabled,
  subscribeHaptics,
} from '@/lib/haptics';
import type { BaseSettingsProps } from '@/types/settings';

/**
 * The sensory switch — a preference of its own, not a corollary of motion.
 *
 * `prefers-reduced-motion` says the reader wants fewer ANIMATIONS. It says
 * nothing about touch, and someone may legitimately want a still interface
 * WITH tactile confirmation, or the reverse. Deriving one from the other would
 * decide for them, so this is its own control.
 *
 * Device-scoped: the same account on a laptop has no vibration motor, so the
 * preference lives in `localStorage` beside the theme and the font rather than
 * in the database, which would propagate a phone's answer to every screen.
 *
 * Renders NOTHING where the capability is absent (iOS Safari, desktop): a
 * switch that cannot change anything is worse than no switch — it invites the
 * reader to fix something that was never broken.
 */
export function HapticsSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  // `navigator` and `localStorage` are client-only, so the value is read
  // through the external store rather than copied into React state from an
  // effect: the server snapshot is explicit (no hydration mismatch), and no
  // `setState` runs inside an effect.
  const supported = useSyncExternalStore(subscribeHaptics, isHapticsSupported, () => false);
  const enabled = useSyncExternalStore(subscribeHaptics, areHapticsEnabled, () => true);

  if (!supported) return null;

  const content = (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0 space-y-0.5">
        <Label htmlFor="haptics-enabled" className="text-sm font-medium">
          {t('settings.haptics.label')}
        </Label>
        <p className="text-xs text-muted-foreground">{t('settings.haptics.description')}</p>
      </div>
      <Switch id="haptics-enabled" checked={enabled} onCheckedChange={setHapticsEnabled} />
    </div>
  );

  return (
    <SettingsSection
      value="haptics"
      title={t('settings.haptics.title')}
      description={t('settings.haptics.description')}
      icon={Vibrate}
    >
      {content}
    </SettingsSection>
  );
}

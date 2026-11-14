'use client';

import { useTranslation } from 'react-i18next';
import { Switch } from '@/components/ui/switch';

interface SpaceActivationToggleProps {
  isActive: boolean;
  onToggle: () => void;
  /** The space's activation is being saved: the switch stays focusable (`Switch`'s `busy`). */
  busy?: boolean;
}

export function SpaceActivationToggle({
  isActive,
  onToggle,
  busy,
}: SpaceActivationToggleProps) {
  const { t } = useTranslation();

  return (
    <Switch
      checked={isActive}
      onCheckedChange={onToggle}
      busy={busy}
      aria-label={isActive ? t('spaces.deactivate') : t('spaces.activate')}
      onClick={e => e.stopPropagation()}
    />
  );
}

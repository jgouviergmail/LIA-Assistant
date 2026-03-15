'use client';

import { useTranslation } from 'react-i18next';
import { Switch } from '@/components/ui/switch';

interface SpaceActivationToggleProps {
  isActive: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function SpaceActivationToggle({ isActive, onToggle, disabled }: SpaceActivationToggleProps) {
  const { t } = useTranslation();

  return (
    <Switch
      checked={isActive}
      onCheckedChange={onToggle}
      disabled={disabled}
      aria-label={isActive ? t('spaces.deactivate') : t('spaces.activate')}
      onClick={(e) => e.stopPropagation()}
    />
  );
}

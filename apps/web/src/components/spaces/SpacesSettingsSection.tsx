'use client';

/**
 * The settings section « Knowledge spaces »: the management screen itself,
 * never an intermediate list pointing at it (owner, 2026-10-03). The screen
 * is `SpacesManager`, shared with `/dashboard/spaces`.
 */

import { Library } from 'lucide-react';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { SpacesManager } from '@/components/spaces/SpacesManager';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

interface SpacesSettingsSectionProps {
  lng: string;
}

export function SpacesSettingsSection({ lng }: SpacesSettingsSectionProps) {
  const { t } = useTranslation(lng as Language);

  return (
    <SettingsSection
      value="rag-spaces"
      title={t('settings.rag_spaces.title')}
      description={t('settings.rag_spaces.description')}
      icon={Library}
    >
      <SpacesManager variant="section" />
    </SettingsSection>
  );
}

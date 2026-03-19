'use client';

import { Library } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useSpaces } from '@/hooks/useSpaces';
import { useTranslation } from '@/i18n/client';
import Link from 'next/link';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

interface SpacesSettingsSectionProps {
  lng: string;
}

export function SpacesSettingsSection({ lng }: SpacesSettingsSectionProps) {
  const { t } = useTranslation(lng as Language);
  const { spaces, loading, toggleSpace, toggling } = useSpaces();

  return (
    <SettingsSection
      value="rag-spaces"
      title={t('settings.rag_spaces.title')}
      description={t('settings.rag_spaces.description')}
      icon={Library}
    >
      {loading ? (
        <div className="flex items-center justify-center py-6">
          <LoadingSpinner size="lg" />
        </div>
      ) : spaces.length === 0 ? (
        <div className="text-center py-6">
          <p className="text-sm text-muted-foreground mb-3">{t('settings.rag_spaces.no_spaces')}</p>
          <Link
            href={buildLocalizedPath('/dashboard/spaces', lng as Language)}
            className="text-sm text-primary hover:underline"
          >
            {t('settings.rag_spaces.create_first')}
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-3">
            {spaces.map(space => (
              <div
                key={space.id}
                className="flex items-center justify-between rounded-lg border p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{space.name}</p>
                  {space.description && (
                    <p className="text-xs text-muted-foreground truncate">{space.description}</p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {space.document_count}{' '}
                    {space.document_count === 1
                      ? t('spaces.doc_singular')
                      : t('spaces.docs_plural')}
                  </p>
                </div>
                <Switch
                  checked={space.is_active}
                  onCheckedChange={() => toggleSpace(space.id)}
                  disabled={toggling}
                />
              </div>
            ))}
          </div>
          <div className="text-center pt-2">
            <Link
              href={buildLocalizedPath('/dashboard/spaces', lng as Language)}
              className="text-sm text-primary hover:underline"
            >
              {t('settings.rag_spaces.manage_all')}
            </Link>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}

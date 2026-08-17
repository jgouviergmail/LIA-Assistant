'use client';

/**
 * DocumentGenerationSettings - per-user opt-in for AI document generation
 * (ADR-226). One toggle, mirroring the ImageGenerationSettings enable switch:
 * the model/limits are administrated server-side (LLM Config + capability
 * switch), so the user surface is deliberately a single choice.
 */

import { useState } from 'react';
import { FileOutput } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

export function DocumentGenerationSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [updating, setUpdating] = useState(false);

  const updatePreference = async (value: boolean) => {
    // The guard (not a disabled attribute) prevents the double submit — a
    // control disabled while focused is blurred and dropped from the tab
    // order (frontend contract, PeerConnectionsSettings lesson).
    if (!user || updating) return;

    setUpdating(true);
    try {
      await apiClient.patch(`/users/${user.id}`, { document_generation_enabled: value });
      await refreshUser();
      toast.success(t('settings.document_generation.updated'));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdating(false);
    }
  };

  const content = (
    <div className="space-y-4">
      <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
        <div className="flex-1">
          <p className="text-sm font-medium">{t('settings.document_generation.enable')}</p>
          <p className="text-xs text-muted-foreground">
            {t('settings.document_generation.enable_description')}
          </p>
        </div>
        <Switch
          checked={user?.document_generation_enabled ?? false}
          onCheckedChange={updatePreference}
          aria-disabled={updating}
          aria-label={t('settings.document_generation.enable')}
        />
      </div>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="document-generation"
      icon={FileOutput}
      title={t('settings.document_generation.title')}
      description={t('settings.document_generation.description')}
    >
      {content}
    </SettingsSection>
  );
}

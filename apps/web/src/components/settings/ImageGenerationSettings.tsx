'use client';

/**
 * ImageGenerationSettings - Settings component for AI image generation preferences.
 *
 * Provides controls for:
 * - Enable/disable image generation (per-user opt-in)
 * - Default quality selection (low/medium/high with pricing)
 * - Default size selection (square/landscape/portrait)
 * - Default output format (PNG/JPEG/WebP)
 *
 * Phase: evolution — AI Image Generation
 */

import { useState } from 'react';
import { ImageIcon } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

export function ImageGenerationSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [updating, setUpdating] = useState(false);

  const updatePreference = async (field: string, value: string | boolean) => {
    if (!user || updating) return;

    setUpdating(true);
    try {
      await apiClient.patch(`/users/${user.id}`, { [field]: value });
      await refreshUser();
      toast.success(t('settings.image_generation.updated'));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdating(false);
    }
  };

  const content = (
    <div className="space-y-4">
      {/* Enable toggle */}
      <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
        <div className="flex-1">
          <p className="text-sm font-medium">{t('settings.image_generation.enable')}</p>
          <p className="text-xs text-muted-foreground">
            {t('settings.image_generation.enable_description')}
          </p>
        </div>
        <Switch
          checked={(user as any)?.image_generation_enabled ?? false}
          onCheckedChange={checked => updatePreference('image_generation_enabled', checked)}
          disabled={updating}
        />
      </div>

      {/* Quality selector */}
      <div className="p-3 rounded-lg border bg-card space-y-2">
        <p className="text-sm font-medium">{t('settings.image_generation.quality')}</p>
        <Select
          value={(user as any)?.image_generation_default_quality ?? 'medium'}
          onValueChange={value => updatePreference('image_generation_default_quality', value)}
          disabled={updating}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">
              {t('settings.image_generation.quality_low')} (~$0.01-0.02)
            </SelectItem>
            <SelectItem value="medium">
              {t('settings.image_generation.quality_medium')} (~$0.04-0.06)
            </SelectItem>
            <SelectItem value="high">
              {t('settings.image_generation.quality_high')} (~$0.17-0.25)
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Size selector */}
      <div className="p-3 rounded-lg border bg-card space-y-2">
        <p className="text-sm font-medium">{t('settings.image_generation.size')}</p>
        <Select
          value={(user as any)?.image_generation_default_size ?? '1024x1024'}
          onValueChange={value => updatePreference('image_generation_default_size', value)}
          disabled={updating}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1024x1024">
              {t('settings.image_generation.size_square')} (1024x1024)
            </SelectItem>
            <SelectItem value="1536x1024">
              {t('settings.image_generation.size_landscape')} (1536x1024)
            </SelectItem>
            <SelectItem value="1024x1536">
              {t('settings.image_generation.size_portrait')} (1024x1536)
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Format selector */}
      <div className="p-3 rounded-lg border bg-card space-y-2">
        <p className="text-sm font-medium">{t('settings.image_generation.format')}</p>
        <Select
          value={(user as any)?.image_generation_output_format ?? 'png'}
          onValueChange={value => updatePreference('image_generation_output_format', value)}
          disabled={updating}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="png">PNG</SelectItem>
            <SelectItem value="jpeg">JPEG</SelectItem>
            <SelectItem value="webp">WebP</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="image-generation"
      icon={ImageIcon}
      title={t('settings.image_generation.title')}
      description={t('settings.image_generation.description')}
    >
      {content}
    </SettingsSection>
  );
}

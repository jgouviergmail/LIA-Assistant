'use client';

/**
 * ImageGenerationSettings - Settings component for AI image generation preferences.
 *
 * Provides controls for:
 * - Enable/disable image generation (per-user opt-in)
 * - Default quality selection (driven by /image-generation/options)
 * - Default size selection (driven by /image-generation/options)
 * - Default output format (PNG/JPEG/WebP — purely client-side, unrelated to pricing)
 *
 * The qualities and sizes are NOT hardcoded anymore — they come from the
 * ``image_generation_pricing`` table via the ``/image-generation/options``
 * endpoint, so adding a new pricing row in admin Tarification LLM Image
 * makes the new options available immediately.
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
import { Skeleton } from '@/components/ui/skeleton';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import { useImageGenerationOptions } from '@/hooks/useImageGenerationOptions';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

export function ImageGenerationSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [updating, setUpdating] = useState(false);

  const { data: options, loading, error } = useImageGenerationOptions();

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

  // Resolve the user's saved defaults against the currently-available options.
  // If a stored value is no longer available (e.g. admin removed the pricing
  // row for that quality/size combination), silently fall back to the first
  // available option. The next user change will persist the new value.
  const userQuality = user?.image_generation_default_quality ?? null;
  const validQuality =
    options?.qualities.find(q => q.value === userQuality)?.value ??
    options?.qualities[0]?.value ??
    'medium';

  const userSize = user?.image_generation_default_size ?? null;
  const validSize =
    options?.sizes.find(s => s.value === userSize)?.value ??
    options?.sizes[0]?.value ??
    '1024x1024';

  const formatPrice = (q: { min_cost_usd: number; max_cost_usd: number }) => {
    if (q.min_cost_usd === q.max_cost_usd) {
      return `~$${q.min_cost_usd.toFixed(2)}`;
    }
    return `~$${q.min_cost_usd.toFixed(2)}-${q.max_cost_usd.toFixed(2)}`;
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
          checked={user?.image_generation_enabled ?? false}
          onCheckedChange={checked => updatePreference('image_generation_enabled', checked)}
          disabled={updating}
        />
      </div>

      {/* Loading state for pricing-driven dropdowns */}
      {loading && (
        <>
          <div className="p-3 rounded-lg border bg-card space-y-2">
            <p className="text-sm font-medium">{t('settings.image_generation.quality')}</p>
            <Skeleton className="h-10 w-full" />
          </div>
          <div className="p-3 rounded-lg border bg-card space-y-2">
            <p className="text-sm font-medium">{t('settings.image_generation.size')}</p>
            <Skeleton className="h-10 w-full" />
          </div>
        </>
      )}

      {/* Error state — no active pricing for the configured model */}
      {!loading && error && (
        <div className="p-3 rounded-lg border border-destructive/40 bg-destructive/10 text-sm text-destructive">
          {t('settings.image_generation.options_unavailable')}
        </div>
      )}

      {/* Quality selector — driven by /image-generation/options */}
      {!loading && !error && options && options.qualities.length > 0 && (
        <div className="p-3 rounded-lg border bg-card space-y-2">
          <p className="text-sm font-medium">{t('settings.image_generation.quality')}</p>
          <Select
            value={validQuality}
            onValueChange={value => updatePreference('image_generation_default_quality', value)}
            disabled={updating}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.qualities.map(q => (
                <SelectItem key={q.value} value={q.value}>
                  {t(`settings.image_generation.quality_${q.value}`, { defaultValue: q.value })} (
                  {formatPrice(q)})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Size selector — driven by /image-generation/options */}
      {!loading && !error && options && options.sizes.length > 0 && (
        <div className="p-3 rounded-lg border bg-card space-y-2">
          <p className="text-sm font-medium">{t('settings.image_generation.size')}</p>
          <Select
            value={validSize}
            onValueChange={value => updatePreference('image_generation_default_size', value)}
            disabled={updating}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.sizes.map(s => (
                <SelectItem key={s.value} value={s.value}>
                  {t(s.label_key, { defaultValue: s.value })} ({s.value})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Format selector — purely client-side, unrelated to pricing */}
      <div className="p-3 rounded-lg border bg-card space-y-2">
        <p className="text-sm font-medium">{t('settings.image_generation.format')}</p>
        <Select
          value={user?.image_generation_output_format ?? 'png'}
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

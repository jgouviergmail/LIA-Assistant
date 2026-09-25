'use client';

/**
 * ImageGenerationSettings - Settings component for AI image generation preferences.
 *
 * Provides controls for:
 * - Enable/disable image generation (per-user opt-in)
 * - Default quality selection (driven by /image-generation/options)
 * - Default size selection (driven by /image-generation/options)
 * - Default output format (PNG/JPEG/WebP — the server converts every image into it)
 * - Prompt enhancement (ADR-315): an opt-in rewrite of each generation prompt,
 *   shown only when the operator offers it (``prompt_enhancement_available``)
 *
 * The qualities and sizes come from what the configured model offers (ADR-305):
 * each vendor has its own vocabulary, and a size carries its orientation and,
 * for a vendor that bills by resolution, its tier (1K/2K).
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
import {
  useImageGenerationOptions,
  type ImageGenerationOptions,
  type SizeOption,
} from '@/hooks/useImageGenerationOptions';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { User } from '@/lib/auth';
import type { BaseSettingsProps } from '@/types/settings';

export function ImageGenerationSettings({ lng }: BaseSettingsProps) {
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

  // The server maps a stored preference onto what the configured model offers
  // (ADR-305) and publishes the result as ``effective_*``. A stored value the
  // model offers is exactly what the server keeps, so it is shown at once after
  // a change; one it does not offer is shown as the server's mapping of it.
  const userQuality = user?.image_generation_default_quality ?? null;
  const shownQuality =
    options?.qualities.find(q => q.value === userQuality)?.value ?? options?.effective_quality;

  const userSize = user?.image_generation_default_size ?? null;
  const shownSize =
    options?.sizes.find(s => s.value === userSize)?.value ?? options?.effective_size;

  const sizeLabel = (s: SizeOption) => {
    const name = t(s.label_key, { defaultValue: s.value });
    return s.tier ? `${name} · ${s.tier.toUpperCase()} (${s.value})` : `${name} (${s.value})`;
  };

  const formatPrice = (q: { min_cost_usd: number; max_cost_usd: number }) => {
    if (q.min_cost_usd === q.max_cost_usd) {
      return `~$${q.min_cost_usd.toFixed(2)}`;
    }
    return `~$${q.min_cost_usd.toFixed(2)}-${q.max_cost_usd.toFixed(2)}`;
  };

  const content = (
    <div className="space-y-4">
      {/* Enable toggle */}
      <div className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card">
        <div className="flex-1">
          <p id="image-generation-enable-label" className="text-sm font-medium">
            {t('settings.image_generation.enable')}
          </p>
          <p id="image-generation-enable-description" className="text-xs text-muted-foreground">
            {t('settings.image_generation.enable_description')}
          </p>
        </div>
        <Switch
          aria-labelledby="image-generation-enable-label"
          aria-describedby="image-generation-enable-description"
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

      {/* Error state — the configured model is not served (no family or no active price) */}
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
            value={shownQuality}
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
            value={shownSize}
            onValueChange={value => updatePreference('image_generation_default_size', value)}
            disabled={updating}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.sizes.map(s => (
                <SelectItem key={s.value} value={s.value}>
                  {sizeLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Format selector — every generated or edited image is delivered in it */}
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

      <PromptEnhancementRow
        lng={lng}
        offered={enhancementOffered({ loading, error, options })}
        user={user}
        disabled={updating}
        onChange={checked => updatePreference('image_generation_prompt_enhancement', checked)}
      />
    </div>
  );

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

/**
 * Whether the enhancement switch is shown (ADR-315): only once the options are
 * read, and only when the operator offers it — the page never offers what the
 * image tool would ignore. Module-level and pure (the complexity ratchet).
 */
function enhancementOffered(state: {
  loading: boolean;
  error: Error | null;
  options: ImageGenerationOptions | undefined;
}): boolean {
  return !state.loading && !state.error && Boolean(state.options?.prompt_enhancement_available);
}

/** The person's opt-in for rewriting their generation prompts (ADR-315). */
function PromptEnhancementRow({
  lng,
  offered,
  user,
  disabled,
  onChange,
}: {
  lng: BaseSettingsProps['lng'];
  offered: boolean;
  /** Whose opt-in — read here so the section's render stays flat (the CC ratchet). */
  user: User | null;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  const { t } = useTranslation(lng);
  if (!offered) return null;
  return (
    <div className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card">
      <div className="flex-1">
        <p id="image-generation-enhancement-label" className="text-sm font-medium">
          {t('settings.image_generation.prompt_enhancement')}
        </p>
        <p id="image-generation-enhancement-description" className="text-xs text-muted-foreground">
          {t('settings.image_generation.prompt_enhancement_description')}
        </p>
      </div>
      <Switch
        aria-labelledby="image-generation-enhancement-label"
        aria-describedby="image-generation-enhancement-description"
        checked={user?.image_generation_prompt_enhancement ?? false}
        onCheckedChange={onChange}
        disabled={disabled}
      />
    </div>
  );
}

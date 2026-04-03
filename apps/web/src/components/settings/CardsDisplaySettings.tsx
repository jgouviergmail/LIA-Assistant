'use client';

import { useState } from 'react';
import { LayoutGrid, FileText, Type } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

import type { BaseSettingsProps } from '@/types/settings';

const DISPLAY_MODES = [
  { value: 'cards', icon: LayoutGrid },
  { value: 'html', icon: FileText },
  { value: 'markdown', icon: Type },
] as const;

export function CardsDisplaySettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [updating, setUpdating] = useState(false);

  const currentMode = user?.response_display_mode ?? 'cards';

  const handleModeChange = async (mode: string) => {
    if (!user || updating || mode === currentMode) return;

    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/display-mode-preference', {
        response_display_mode: mode,
      });

      await refreshUser();
      toast.success(t(`settings.preferences.display_mode.modes.${mode}.selected`));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdating(false);
    }
  };

  const content = (
    <div className="space-y-4">
      {/* Mode selector */}
      <div className="grid grid-cols-3 gap-2">
        {DISPLAY_MODES.map(({ value, icon: Icon }) => (
          <button
            key={value}
            onClick={() => handleModeChange(value)}
            disabled={updating}
            className={cn(
              'flex flex-col items-center gap-2 p-3 rounded-lg border transition-all',
              'hover:border-primary/50 hover:bg-accent/50',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              currentMode === value
                ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                : 'border-border bg-card'
            )}
          >
            <Icon
              className={cn(
                'h-5 w-5',
                currentMode === value ? 'text-primary' : 'text-muted-foreground'
              )}
            />
            <span
              className={cn(
                'text-xs font-medium',
                currentMode === value ? 'text-primary' : 'text-muted-foreground'
              )}
            >
              {t(`settings.preferences.display_mode.modes.${value}.label`)}
            </span>
          </button>
        ))}
      </div>

      {/* Active mode description */}
      <p className="text-xs text-muted-foreground px-1">
        {t(`settings.preferences.display_mode.modes.${currentMode}.description`)}
      </p>

      {/* Info */}
      <InfoBox>
        <p className="text-xs text-muted-foreground">
          {t('settings.preferences.display_mode.info')}
        </p>
      </InfoBox>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="display-mode"
      title={t('settings.preferences.display_mode.title')}
      description={t('settings.preferences.display_mode.description')}
      icon={LayoutGrid}
    >
      {content}
    </SettingsSection>
  );
}

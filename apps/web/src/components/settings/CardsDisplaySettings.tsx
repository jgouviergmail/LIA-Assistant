'use client';

import { useId, useRef, useState } from 'react';
import { LayoutGrid, FileText, PanelsTopLeft, Type } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { ResponseDisplayPreview } from '@/components/settings/ResponseDisplayPreview';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

import type { BaseSettingsProps, ResponseDisplayMode } from '@/types/settings';

const DISPLAY_MODES = [
  { value: 'cards', icon: LayoutGrid },
  { value: 'html', icon: FileText },
  { value: 'html_cards', icon: PanelsTopLeft },
  { value: 'markdown', icon: Type },
] as const satisfies ReadonlyArray<{ value: ResponseDisplayMode; icon: typeof LayoutGrid }>;

/** A different account starts a fresh local save lifetime. */
export function CardsDisplaySettings(props: BaseSettingsProps) {
  const auth = useAuth();
  return <DisplaySettingsContent key={auth.user?.id ?? 'anonymous'} {...props} auth={auth} />;
}

function DisplaySettingsContent({
  lng,
  auth: { user, refreshUser },
}: BaseSettingsProps & { auth: ReturnType<typeof useAuth> }) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const [pendingMode, setPendingMode] = useState<ResponseDisplayMode | null>(null);
  const inFlight = useRef(false);
  const id = useId();
  const currentMode =
    DISPLAY_MODES.find(mode => mode.value === user?.response_display_mode)?.value ?? 'cards';

  const handleModeChange = async (mode: ResponseDisplayMode) => {
    if (!isCurrent() || inFlight.current || mode === currentMode) return;
    inFlight.current = true;
    setPendingMode(mode);
    try {
      await apiClient.patch('/auth/me/display-mode-preference', { response_display_mode: mode });
      if (!isCurrent()) return;
      const refreshed = await refreshUser();
      if (!isCurrent()) return;
      if (!refreshed) {
        toast.error(t('common.error'));
        return;
      }
      toast.success(t(`settings.preferences.display_mode.modes.${mode}.selected`));
    } catch {
      if (isCurrent()) toast.error(t('common.error'));
    } finally {
      inFlight.current = false;
      if (isCurrent()) setPendingMode(null);
    }
  };

  return (
    <SettingsSection
      value="display-mode"
      title={t('settings.preferences.display_mode.title')}
      description={t('settings.preferences.display_mode.description')}
      icon={LayoutGrid}
    >
      <div className="space-y-5">
        <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(11rem,0.7fr)_minmax(0,2fr)]">
          <fieldset className="min-w-0 space-y-2">
            <legend className="sr-only">
              {t('settings.preferences.display_mode.description')}
            </legend>
            {DISPLAY_MODES.map(({ value, icon: Icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => void handleModeChange(value)}
                aria-pressed={currentMode === value}
                aria-disabled={pendingMode !== null || !user}
                aria-busy={pendingMode === value || undefined}
                aria-labelledby={`${id}-${value}`}
                className={cn(
                  'flex min-h-14 w-full min-w-0 items-center gap-3 rounded-xl border p-3 text-left text-sm font-medium transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                  'aria-disabled:cursor-not-allowed',
                  currentMode === value
                    ? 'border-primary/40 bg-primary/10 text-foreground'
                    : 'border-border/60 bg-card hover:border-primary/40 hover:bg-primary/5'
                )}
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/8 text-primary">
                  {pendingMode === value ? (
                    <LoadingSpinner aria-hidden="true" />
                  ) : (
                    <Icon className="size-4" aria-hidden="true" />
                  )}
                </span>
                <span id={`${id}-${value}`} className="min-w-0 break-words leading-relaxed">
                  {t(`settings.preferences.display_mode.modes.${value}.label`)}
                </span>
              </button>
            ))}
          </fieldset>
          <section
            aria-label={t('settings.preferences.display_mode.preview.title')}
            className="min-w-0 space-y-4 rounded-2xl border border-border/60 bg-muted/20 p-4 sm:p-5"
          >
            <p className="break-words text-sm leading-relaxed text-muted-foreground">
              {t(`settings.preferences.display_mode.modes.${currentMode}.description`)}
            </p>
            <ResponseDisplayPreview mode={currentMode} lng={lng} />
          </section>
        </div>
      </div>
    </SettingsSection>
  );
}

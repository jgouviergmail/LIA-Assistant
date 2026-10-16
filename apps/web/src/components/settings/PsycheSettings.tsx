'use client';

import { useId, useRef, useState } from 'react';
import {
  BookOpen,
  Brain,
  ChartLine,
  RefreshCw,
  RotateCcw,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import { usePsyche } from '@/hooks/usePsyche';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PsycheSettings as PsychePreferencesData, PsycheSettingsUpdate } from '@/types/psyche';
import { PsycheLLMSummary } from '@/components/psyche/PsycheLLMSummary';
import { PsycheStateSummary } from '@/components/psyche/PsycheStateSummary';
import { PsycheEducation } from '@/components/psyche/PsycheEducation';
import { PsycheHistory } from '@/components/psyche/PsycheHistory';
import { SettingsSection } from './SettingsSection';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Card } from '@/components/ui/card';
import { Disclosure } from '@/components/ui/disclosure';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';

interface PsycheSettingsProps {
  lng: Language;
}

export function PsycheSettings(props: PsycheSettingsProps) {
  const { user } = useAuth();
  return <OwnedPsycheSettings key={user?.id ?? 'anonymous'} {...props} ownerId={user?.id} />;
}

function OwnedPsycheSettings({
  lng,
  ownerId,
}: PsycheSettingsProps & { ownerId: string | undefined }) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const {
    settings,
    state,
    error,
    settingsError,
    isLoading,
    isUpdatingSettings,
    isResetting,
    updateSettings,
    resetPsyche,
    refetchState,
    refetchSettings,
  } = usePsyche();
  const [openObservations, setOpen] = useState<string[]>(['evolution']);
  const [summaryOpen, setSummaryOpen] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [resetVersion, setResetVersion] = useState(0);
  const [pending, setPending] = useState(false);
  const lock = useRef(false);
  const busy = pending || isUpdatingSettings || isResetting;

  const perform = async <T,>(
    operation: () => Promise<T | null | undefined>,
    successKey: string,
    errorKey: string
  ): Promise<T | null> => {
    if (!isCurrent() || lock.current || isUpdatingSettings || isResetting) return null;
    lock.current = true;
    setPending(true);
    try {
      const result = await operation();
      if (!isCurrent() || result === null) return null;
      if (!result) throw new Error('Psyche mutation was not acknowledged');
      toast.success(t(successKey));
      return result;
    } catch {
      if (isCurrent()) toast.error(t(errorKey));
      return null;
    } finally {
      lock.current = false;
      if (isCurrent()) setPending(false);
    }
  };
  const save = (data: PsycheSettingsUpdate) =>
    perform(() => updateSettings(data), 'psyche.settingsUpdated', 'psyche.settingsError');
  const reset = async (level: 'soft' | 'full') => {
    const result = await perform(
      () => resetPsyche(level),
      'psyche.resetSuccess',
      'psyche.resetError'
    );
    if (result && isCurrent()) {
      setResetVersion(value => value + 1);
      setRefreshKey(value => value + 1);
    }
  };
  const refresh = async () => {
    if (!isCurrent() || lock.current || busy) return;
    lock.current = true;
    setPending(true);
    try {
      await Promise.all([refetchState(), refetchSettings()]);
      if (isCurrent()) setRefreshKey(value => value + 1);
    } catch {
      if (isCurrent()) toast.error(t('psyche.presentation.readError'));
    } finally {
      lock.current = false;
      if (isCurrent()) setPending(false);
    }
  };
  return (
    <SettingsSection
      value="psyche"
      icon={Brain}
      title={<PsycheHeading lng={lng} settings={settings} busy={busy || !ownerId} save={save} />}
      description={t('psyche.description')}
    >
      <div className="min-w-0 space-y-5">
        <Button
          size="sm"
          onClick={() => void refresh()}
          aria-disabled={busy || !ownerId}
          aria-busy={pending || undefined}
          className="min-h-10 w-full whitespace-normal sm:w-auto"
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          {t('common.refresh')}
        </Button>
        {error && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm leading-relaxed"
          >
            {t('psyche.presentation.readError')}
          </p>
        )}
        {!settings && isLoading && (
          <Skeleton label={t('common.loading')} className="h-44 w-full rounded-xl" />
        )}
        {settings && (
          <>
            <Accordion type="multiple" className="w-full space-y-3">
              <PsychePanel value="education" title={t('psyche.education.title')} icon={BookOpen}>
                <PsycheEducation lng={lng} />
              </PsychePanel>
              <PsychePanel
                value="preferences"
                title={t('psyche.settingsSection.title')}
                icon={SlidersHorizontal}
              >
                <PsychePreferences lng={lng} settings={settings} busy={busy} save={save} />
              </PsychePanel>
              <PsychePanel value="resets" title={t('psyche.presentation.resets')} icon={RotateCcw}>
                <PsycheResets lng={lng} busy={busy} reset={reset} />
              </PsychePanel>
            </Accordion>
            {settings.psyche_enabled && (
              <>
                <PsycheStateSummary
                  lng={lng}
                  summary={
                    <Disclosure
                      surface="primary"
                      className="border-border/60 px-3"
                      icon={Sparkles}
                      title={t('psyche.presentation.point')}
                      titleClassName="text-base font-semibold whitespace-normal"
                      defaultOpen
                      onOpenChange={setSummaryOpen}
                    >
                      <PsycheLLMSummary
                        key={resetVersion}
                        lng={lng}
                        isOpen={summaryOpen}
                        hideHeading
                        refreshKey={refreshKey}
                        onGenerated={() => {
                          if (!state && isCurrent()) void refetchState().catch(() => {});
                        }}
                      />
                    </Disclosure>
                  }
                />
                <Accordion
                  type="multiple"
                  value={openObservations}
                  onValueChange={setOpen}
                  className="w-full space-y-4"
                >
                  <PsychePanel
                    value="evolution"
                    title={t('psyche.presentation.evolution')}
                    icon={ChartLine}
                  >
                    <PsycheHistory
                      lng={lng}
                      isOpen={openObservations.includes('evolution')}
                      refreshKey={refreshKey}
                    />
                  </PsychePanel>
                </Accordion>
              </>
            )}
            {settingsError && (
              <p className="text-xs text-muted-foreground">{t('psyche.presentation.retained')}</p>
            )}
          </>
        )}
      </div>
    </SettingsSection>
  );
}

function PsychePanel({
  value,
  title,
  icon: Icon,
  children,
}: {
  value: string;
  title: string;
  icon: typeof Brain;
  children: React.ReactNode;
}) {
  return (
    <Card surface="nested" variant="flat" className="min-w-0 px-3 sm:px-4">
      <AccordionItem value={value} className="min-w-0 border-0">
        <AccordionTrigger className="gap-3 py-4 text-left text-base font-semibold hover:no-underline">
          <span className="flex min-w-0 items-center gap-2">
            <Icon className="size-5 shrink-0 text-primary" aria-hidden="true" />
            <span className="min-w-0 [overflow-wrap:anywhere]">{title}</span>
          </span>
        </AccordionTrigger>
        <AccordionContent className="min-w-0 pb-4">{children}</AccordionContent>
      </AccordionItem>
    </Card>
  );
}

function PsychePreferences({
  lng,
  settings,
  busy,
  save,
}: {
  lng: Language;
  settings: PsychePreferencesData;
  busy: boolean;
  save: (data: PsycheSettingsUpdate) => Promise<PsychePreferencesData | null>;
}) {
  const { t } = useTranslation(lng);
  const avatarId = useId();
  const [draft, setDraft] = useState<Partial<PsychePreferencesData>>({});
  const commit = async (field: 'psyche_sensitivity' | 'psyche_stability', value: number) => {
    if (busy) return;
    await save({ [field]: value });
    setDraft(current => ({ ...current, [field]: undefined }));
  };
  return (
    <div className="space-y-5 pt-1">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-2">
          <Label htmlFor={avatarId} className="text-sm leading-relaxed">
            {t('psyche.displayAvatar')}
          </Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t('psyche.displayAvatarDescription')}
          </p>
        </div>
        <Switch
          id={avatarId}
          checked={settings.psyche_display_avatar}
          onCheckedChange={value => {
            if (!busy) void save({ psyche_display_avatar: value });
          }}
          aria-disabled={busy}
          className="mt-1 shrink-0"
        />
      </div>
      {(['psyche_sensitivity', 'psyche_stability'] as const).map(field => {
        const key = field === 'psyche_sensitivity' ? 'sensitivity' : 'stability';
        const value = draft[field] ?? settings[field];
        return (
          <div key={field} className="space-y-3 border-t border-border/50 pt-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium">{t(`psyche.${key}`)}</span>
              <span className="shrink-0 text-sm tabular-nums text-primary">{value}%</span>
            </div>
            <Slider
              value={[value]}
              min={0}
              max={100}
              step={5}
              onValueChange={([next]) => {
                if (!busy) setDraft(current => ({ ...current, [field]: next }));
              }}
              onValueCommit={([next]) => void commit(field, next)}
              aria-disabled={busy}
              aria-label={t(`psyche.${key}`)}
            />
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t(`psyche.${key}Description`)}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function PsycheResets({
  lng,
  busy,
  reset,
}: {
  lng: Language;
  busy: boolean;
  reset: (level: 'soft' | 'full') => Promise<void>;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-5 pt-1">
      {(['soft', 'full'] as const).map(level => {
        const key = level === 'soft' ? 'softReset' : 'fullReset';
        return (
          <div key={level} className="space-y-3">
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t(`psyche.${key}Description`)}
            </p>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  size="sm"
                  variant={level === 'full' ? 'destructive' : 'default'}
                  aria-disabled={busy}
                  onClick={event => {
                    if (busy) event.preventDefault();
                  }}
                  className="min-h-10 max-w-full whitespace-normal"
                >
                  <RotateCcw className="size-4 shrink-0" aria-hidden="true" />
                  {t(`psyche.${key}`)}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t(`psyche.${key}Title`)}</AlertDialogTitle>
                  <AlertDialogDescription>{t(`psyche.${key}Confirm`)}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                  <AlertDialogAction
                    variant={level === 'full' ? 'destructive' : 'default'}
                    onClick={() => void reset(level)}
                  >
                    {t(`psyche.${key}`)}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        );
      })}
    </div>
  );
}

function PsycheHeading({
  lng,
  settings,
  busy,
  save,
}: {
  lng: Language;
  settings: PsychePreferencesData | undefined;
  busy: boolean;
  save: (data: PsycheSettingsUpdate) => Promise<PsychePreferencesData | null>;
}) {
  const { t } = useTranslation(lng);
  return (
    <span className="flex min-w-0 items-center justify-between gap-3">
      <span>{t('psyche.title')}</span>
      <Switch
        checked={settings?.psyche_enabled ?? false}
        onCheckedChange={value => {
          if (settings && !busy) void save({ psyche_enabled: value });
        }}
        aria-disabled={busy || !settings}
        aria-label={t('psyche.enable')}
        className="shrink-0"
      />
    </span>
  );
}

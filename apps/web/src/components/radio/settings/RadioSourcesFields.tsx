'use client';

/**
 * The listener's newsroom (ADR-324 decision 38): every base source, ticked by
 * default — everything airs translated into their language, so there is no kind
 * of news nor language to choose — and the sites they add. Each source says what
 * it published within the window and how many of those stories the listener
 * never heard (counted by the API, never here), and a failing one says so. The
 * totals are what the station can air, and « forget what I heard » lets every
 * story air again (after a confirmation: it cannot be undone).
 *
 * Ticking a base source saves the settings, then reads the newsroom again: the
 * totals move with the choice.
 */
import { Eraser, Library, Newspaper } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import { useRadioSources, type UseRadioSourcesReturn } from '@/hooks/useRadioSources';
import { useTranslation } from '@/i18n/client';
import { sourceLanguageName } from '@/lib/radio/articles';
import { withFeedHeard } from '@/lib/radio/preferences';
import type { RadioBaseSource, RadioOptions, RadioPreferences } from '@/lib/radio/types';
import type { BaseSettingsProps } from '@/types/settings';

import { RadioCustomSources } from './RadioCustomSources';

interface RadioSourcesFieldsProps {
  lng: BaseSettingsProps['lng'];
  options: RadioOptions;
  preferences: RadioPreferences;
  /** Saves the whole new settings; resolves once the save is done (or refused). */
  onChange: (next: RadioPreferences) => Promise<unknown>;
}

export function RadioSourcesFields({
  lng,
  options,
  preferences,
  onChange,
}: RadioSourcesFieldsProps) {
  const { t } = useTranslation(lng);
  const newsroom = useRadioSources();
  const { sources, refresh } = newsroom;
  const tick = async (url: string, heard: boolean) => {
    const next = withFeedHeard(preferences, url, heard);
    if (next === preferences) return;
    await onChange(next);
    await refresh();
  };
  return (
    <Disclosure
      icon={Newspaper}
      title={t('radio.settings.news.title')}
      description={t('radio.settings.news.description')}
    >
      <div className="space-y-4">
        {sources === null ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <>
            <Totals lng={lng} newsroom={newsroom} />
            <BaseSources
              lng={lng}
              base={sources.base}
              unticked={preferences.disabled_feeds}
              onTick={tick}
            />
          </>
        )}
        <RadioCustomSources
          lng={lng}
          newsroom={newsroom}
          max={options.custom_sources_max}
          addressMax={options.source_address_max_chars}
          titleMax={options.source_title_max_chars}
        />
      </div>
    </Disclosure>
  );
}

/** What the station can air, and the way to hear everything again. */
function Totals({
  lng,
  newsroom,
}: {
  lng: BaseSettingsProps['lng'];
  newsroom: UseRadioSourcesReturn;
}) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const { sources, forget, busy } = newsroom;
  if (sources === null) return null;
  const onForget = async () => {
    if (busy) return;
    const accepted = await confirm({
      title: t('radio.settings.news.forget_title'),
      description: t('radio.settings.news.forget_description'),
      confirmLabel: t('radio.settings.news.forget_confirm'),
    });
    if (!accepted) return;
    if (await forget()) toast.success(t('radio.settings.news.forgotten'));
    else toast.error(t('radio.settings.news.forget_failed'));
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-card p-3">
      <p className="text-sm" aria-live="polite">
        {t('radio.settings.news.totals', {
          hours: sources.window_hours,
          stories: sources.stories,
          unheard: sources.unheard,
        })}
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-2"
        aria-disabled={busy || undefined}
        onClick={() => void onForget()}
      >
        <Eraser className="h-4 w-4" aria-hidden="true" />
        {t('radio.settings.news.forget')}
      </Button>
      {confirmDialog}
    </div>
  );
}

/** The shipped catalogue: a checkbox per source, its language and what it holds. */
function BaseSources({
  lng,
  base,
  unticked,
  onTick,
}: {
  lng: BaseSettingsProps['lng'];
  base: RadioBaseSource[];
  unticked: string[];
  onTick: (url: string, heard: boolean) => Promise<void>;
}) {
  const { t } = useTranslation(lng);
  return (
    <fieldset className="space-y-3">
      <legend className="flex items-center gap-2 text-sm font-medium">
        <Library className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('radio.settings.news.base_title')}
      </legend>
      <p className="text-xs text-muted-foreground">{t('radio.settings.news.base_hint')}</p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {base.map((source, index) => {
          const id = `radio-feed-${index}`;
          const hintId = `${id}-hint`;
          return (
            <li key={source.url} className="flex items-start gap-2">
              <Checkbox
                id={id}
                aria-describedby={hintId}
                checked={!unticked.includes(source.url)}
                onChange={event => void onTick(source.url, event.target.checked)}
              />
              <div className="min-w-0 space-y-0.5">
                <Label htmlFor={id} className="break-words">
                  {t('radio.settings.news.with_language', {
                    name: source.name,
                    language: sourceLanguageName(source.language, lng),
                  })}
                </Label>
                <div
                  id={hintId}
                  className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
                >
                  <span>
                    {t('radio.settings.news.counts', {
                      stories: source.stories,
                      unheard: source.unheard,
                    })}
                  </span>
                  {source.failing && (
                    <Badge variant="warning" size="sm">
                      {t('radio.settings.news.failing')}
                    </Badge>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

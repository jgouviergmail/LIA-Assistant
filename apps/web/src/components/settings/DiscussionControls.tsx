'use client';

import { useEffect, useState } from 'react';
import { Clock, Shield, SlidersHorizontal } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { HourWindow } from '@/components/settings/FrequencyControls';
import { Disclosure } from '@/components/ui/disclosure';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  discussionTopics,
  type DiscussionSettings,
  type DiscussionPolicyPatch,
} from '@/types/proactive-discussions';

export function DiscussionControls({
  lng,
  settings,
  busy,
  update,
}: {
  lng: Language;
  settings: DiscussionSettings;
  busy: boolean;
  update: (changes: DiscussionPolicyPatch) => Promise<unknown>;
}) {
  const { t } = useTranslation(lng);
  const { policy } = settings;
  const [draft, setDraft] = useState<{ base: number | null; text: string } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const cap =
    draft && draft.base === policy.daily_max ? draft.text : String(policy.daily_max ?? '');
  const pauseEnd = policy.paused_until === null ? null : Date.parse(policy.paused_until);
  const paused = pauseEnd !== null && pauseEnd > now;
  useEffect(() => {
    if (!paused || pauseEnd === null) return;
    const timer = window.setTimeout(
      () => setNow(Date.now()),
      Math.max(0, Math.min(pauseEnd - Date.now(), 2147000000))
    );
    return () => window.clearTimeout(timer);
  }, [paused, pauseEnd, now]);
  const saveCap = () => {
    const number = Number(cap);
    if (
      !busy &&
      cap.trim() &&
      Number.isSafeInteger(number) &&
      number > 0 &&
      number !== policy.daily_max
    )
      void update({ daily_max: number });
    else setDraft(null);
  };
  return (
    <div className="min-w-0 space-y-5" aria-busy={busy}>
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="discussions-enabled">{t('discussions.enable')}</Label>
        <Switch
          id="discussions-enabled"
          checked={policy.enabled}
          aria-disabled={busy}
          onCheckedChange={enabled => {
            if (!busy) void update({ enabled });
          }}
        />
      </div>
      <HourWindow
        label={
          <>
            <Clock className="h-4 w-4" aria-hidden="true" />
            {t('discussions.hours')}
          </>
        }
        startAriaLabel={t('common.start_hour_label')}
        endAriaLabel={t('common.end_hour_label')}
        startHour={policy.start_hour}
        endHour={policy.end_hour}
        onChange={(field, value) => {
          if (!busy) void update(field === 'start' ? { start_hour: value } : { end_hour: value });
        }}
      />
      <p className="text-xs text-muted-foreground">
        {t('discussions.timezone', { timezone: policy.timezone })}
      </p>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="discussions-unlimited">{t('discussions.unlimited')}</Label>
          <Switch
            id="discussions-unlimited"
            checked={policy.daily_max === null}
            aria-disabled={busy}
            onCheckedChange={unlimited => {
              if (!busy) void update({ daily_max: unlimited ? null : 2 });
            }}
          />
        </div>
        {policy.daily_max !== null && (
          <div className="flex flex-wrap items-center gap-3">
            <Label htmlFor="discussions-daily-max">{t('discussions.daily_max')}</Label>
            <div className="w-24">
              <Input
                id="discussions-daily-max"
                type="number"
                min={1}
                step={1}
                value={cap}
                readOnly={busy}
                className="w-full"
                onChange={event => setDraft({ base: policy.daily_max, text: event.target.value })}
                onBlur={saveCap}
                onKeyDown={event => {
                  if (event.key === 'Enter') event.currentTarget.blur();
                }}
              />
            </div>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t('discussions.limit_hint')}</p>
      </div>
      <Button
        variant="outline"
        aria-disabled={busy}
        onClick={() => {
          if (!busy)
            void update({
              paused_until: paused
                ? null
                : new Date(Date.now() + settings.pause_hours * 3_600_000).toISOString(),
            });
        }}
      >
        {paused ? t('discussions.resume') : t('discussions.pause', { hours: settings.pause_hours })}
      </Button>
      <Disclosure
        title={t('discussions.sources_title')}
        icon={SlidersHorizontal}
        surface="nested"
        badge={policy.sources.length}
      >
        <p className="mb-3 text-sm text-muted-foreground">{t('discussions.sources_hint')}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {settings.sources.map(source => (
            <div
              key={source.key}
              className="flex min-w-0 items-center justify-between gap-3 rounded-lg border bg-card p-3"
            >
              <div className="min-w-0">
                <Label htmlFor={`discussion-source-${source.key}`}>
                  {t(`discussions.sources.${source.key}`)}
                </Label>
                {source.indivisible && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('discussions.portrait_hint')}
                  </p>
                )}
                {source.dependencies.some(key => !policy.sources.includes(key)) && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('discussions.source_requires', {
                      sources: source.dependencies
                        .map(key => t(`discussions.sources.${key}`))
                        .join(', '),
                    })}
                  </p>
                )}
              </div>
              <Switch
                id={`discussion-source-${source.key}`}
                checked={policy.sources.includes(source.key)}
                aria-disabled={busy}
                onCheckedChange={enabled => {
                  if (!busy)
                    void update({
                      sources: enabled
                        ? [...policy.sources, source.key]
                        : policy.sources.filter(key => key !== source.key),
                    });
                }}
              />
            </div>
          ))}
        </div>
      </Disclosure>
      <Disclosure title={t('discussions.topics_title')} icon={Shield} surface="nested">
        <p className="mb-3 text-sm text-muted-foreground">{t('discussions.topics_hint')}</p>
        {/* The sources' panels, in one column (owner request 2026-10-21). */}
        <div className="grid gap-3">
          {discussionTopics.map(topic => (
            <div
              key={topic}
              className="flex min-w-0 items-center justify-between gap-3 rounded-lg border bg-card p-3"
            >
              <Label htmlFor={`discussion-topic-${topic}`}>
                {t(`discussions.topics.${topic}`)}
              </Label>
              <Switch
                id={`discussion-topic-${topic}`}
                checked={policy.sensitive_topics.includes(topic)}
                aria-disabled={busy}
                onCheckedChange={enabled => {
                  if (!busy)
                    void update({
                      sensitive_topics: enabled
                        ? [...policy.sensitive_topics, topic]
                        : policy.sensitive_topics.filter(key => key !== topic),
                    });
                }}
              />
            </div>
          ))}
        </div>
      </Disclosure>
      {policy.forbidden_topics.length > 0 && (
        <Disclosure
          title={t('discussions.forbidden_title')}
          icon={Shield}
          surface="nested"
          badge={policy.forbidden_topics.length}
        >
          <p className="mb-3 text-sm text-muted-foreground">{t('discussions.forbidden_hint')}</p>
          <ul className="grid gap-3">
            {policy.forbidden_topics.map(topic => (
              <li
                key={topic}
                className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3"
              >
                <span className="min-w-0 break-words">{topic}</span>
                <Button
                  variant="outline"
                  size="sm"
                  aria-disabled={busy}
                  onClick={() => {
                    if (!busy)
                      void update({
                        forbidden_topics: policy.forbidden_topics.filter(value => value !== topic),
                      });
                  }}
                >
                  {t('discussions.restore_topic', { topic })}
                </Button>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  );
}

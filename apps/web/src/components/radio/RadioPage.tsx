'use client';

/**
 * The radio's own page (ADR-324): start the station with this session's
 * choices, or follow what it says — the programme on air with its transcript
 * and sources, what comes next, and the articles the session cited, which
 * stay once it is over so a reader finishes the one they opened. The controls
 * and the cost live in the bar under the header, shown on this page like on
 * every other.
 */

import { useEffect, useId, useState } from 'react';
import { Play, Radio, Timer, Users } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isOnAir } from '@/lib/radio/machine';
import { radioPlayer } from '@/lib/radio/player';
import type { RadioStartOptions } from '@/lib/radio/types';
import { useRadioStore } from '@/stores/radioStore';

import { RadioArticles } from './RadioArticles';
import { RadioTranscript } from './RadioTranscript';

/** The automatic stops offered at the start; `default` keeps the listener's setting. */
const TIMER_CHOICES = ['default', '15', '30', '60', '0'] as const;
type TimerChoice = (typeof TIMER_CHOICES)[number];

function isTimerChoice(value: string): value is TimerChoice {
  return (TIMER_CHOICES as readonly string[]).includes(value);
}

/** How often the transcript follows the audio (the line highlight). */
const POSITION_POLL_MS = 500;

/** This session's choices, as the API reads them: only what the listener changed. */
export function startOptions(timer: TimerChoice, company: boolean): RadioStartOptions {
  return {
    ...(timer === 'default' ? {} : { timer_minutes: Number(timer) }),
    ...(company ? { public_mode: true } : {}),
  };
}

function timerLabel(choice: TimerChoice, t: ReturnType<typeof useTranslation>['t']): string {
  if (choice === 'default') return t('radio.page.timer_default');
  if (choice === '0') return t('radio.page.timer_none');
  return t('radio.page.timer_minutes', { count: Number(choice) });
}

function StartCard({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const [timer, setTimer] = useState<TimerChoice>('default');
  const [company, setCompany] = useState(false);
  const timerId = useId();
  const companyId = useId();
  return (
    <section className="space-y-4 rounded-xl border bg-card p-4 shadow-sm">
      <p className="text-sm text-muted-foreground">{t('radio.page.start_description')}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <Label htmlFor={timerId} className="flex items-center gap-2">
            <Timer className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('radio.page.timer_label')}
          </Label>
          <Select
            value={timer}
            onValueChange={value => {
              if (isTimerChoice(value)) setTimer(value);
            }}
          >
            <SelectTrigger id={timerId}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIMER_CHOICES.map(choice => (
                <SelectItem key={choice} value={choice}>
                  {timerLabel(choice, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-3">
          <Label htmlFor={companyId} className="flex items-center gap-2">
            <Users className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('radio.page.company_label')}
          </Label>
          <div className="flex items-center gap-3">
            <Switch id={companyId} checked={company} onCheckedChange={setCompany} />
            <span className="text-xs text-muted-foreground">
              {t('radio.page.company_description')}
            </span>
          </div>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{t('radio.page.cost_note')}</p>
      <Button
        type="button"
        className="gap-2"
        // The click itself starts the station's music: the autoplay rule then
        // lets every segment after it play.
        onClick={() => void radioPlayer().start(startOptions(timer, company))}
      >
        <Play className="h-4 w-4" aria-hidden="true" />
        {t('radio.page.start')}
      </Button>
    </section>
  );
}

/** Seconds into the segment on air, followed while it plays. */
function usePosition(playing: boolean): number {
  const [position, setPosition] = useState(0);
  useEffect(() => {
    if (!playing) return;
    const read = () => setPosition(radioPlayer().position());
    read();
    const timer = window.setInterval(read, POSITION_POLL_MS);
    return () => window.clearInterval(timer);
  }, [playing]);
  return position;
}

function NowPlaying({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const view = useRadioStore(state => state.view);
  const position = usePosition(view.status === 'playing');
  if (view.current === null) {
    return (
      <section className="rounded-xl border bg-card p-4 text-sm text-muted-foreground shadow-sm">
        {t('radio.page.between_programmes')}
      </section>
    );
  }
  return (
    <section className="space-y-3 rounded-xl border bg-card p-4 shadow-sm">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t(`radio.formats.${view.current.format}`)}
        </p>
        <h2 className="text-lg font-semibold">{view.current.title}</h2>
      </div>
      <RadioTranscript lng={lng} segment={view.current} positionS={position} />
      {view.next !== null && (
        <p className="text-sm text-muted-foreground">
          {t('radio.page.next', {
            format: t(`radio.formats.${view.next.format}`),
            title: view.next.title,
          })}
        </p>
      )}
    </section>
  );
}

function SessionArticles({ lng }: { lng: Language }) {
  const articles = useRadioStore(state => state.view.articles);
  return <RadioArticles lng={lng} articles={articles} />;
}

/**
 * @param available - Whether the instance offers the radio now; `null` while
 *   the configuration loads (nothing is offered, nothing is refused yet).
 */
export function RadioPage({ lng, available }: { lng: Language; available: boolean | null }) {
  const { t } = useTranslation(lng);
  const onAir = useRadioStore(state => isOnAir(state.view.status));
  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Radio className="h-6 w-6 text-primary" aria-hidden="true" />
          {t('radio.page.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('radio.page.subtitle')}</p>
      </header>
      {/* A session already on air is followed to its end, switch or not. */}
      {onAir && <NowPlaying lng={lng} />}
      {!onAir && available === true && <StartCard lng={lng} />}
      {!onAir && available === false && (
        <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground shadow-sm">
          {t('radio.page.unavailable')}
        </p>
      )}
      <SessionArticles lng={lng} />
    </div>
  );
}

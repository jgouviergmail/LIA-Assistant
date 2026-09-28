'use client';

/**
 * The radio on screen while it plays (ADR-324): a bar under the header, on
 * every dashboard page, because a station that cannot be seen cannot be
 * stopped — and because what it costs is shown while it spends (a brand value:
 * any surface that spends shows what it spent).
 *
 * Three groups, read left to right: the STATION (its name — the listener's own
 * when they gave it one —, where it stands, what airs), the METERS (the minutes
 * left before the automatic stop; the cost so far and what the planned
 * listening will cost), the ACTIONS (the page with the transcript; pause and
 * stop side by side, the same size in every language — stop keeps its
 * destructive colour at its neighbour's size, ADR-207). The state rides a 4px
 * edge in its colour, the brand's status device. Only where the station stands
 * and what airs are announced (`role="status"`): the cost changes with every
 * report and would chatter under a screen reader. Once the session is over it
 * says why, until dismissed or started again.
 *
 * It sits under the meeting recorder's bar when both show: that bar publishes
 * its height (`--meeting-banner-h`), and this one sticks below it — and
 * publishes its own (`--radio-banner-h`), which the chat's full-height shell
 * subtracts: otherwise the station on air would push the composer below the
 * fold.
 */

import { type ReactNode, type Ref, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Coins,
  FileText,
  Loader2,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Square,
  Timer,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { RadioView } from '@/lib/radio/controller';
import {
  airingSegment,
  minutesLeft,
  radioCost,
  radioEstimateMessage,
  radioStatusMessage,
} from '@/lib/radio/format';
import { radioPlayer } from '@/lib/radio/player';
import { cn } from '@/lib/utils';
import { useRadioStore } from '@/stores/radioStore';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useRadioMediaSession } from './useRadioMediaSession';

/** An inert control looks inert: the Button primitive only dims the `disabled` attribute. */
const INERT = 'aria-disabled:cursor-not-allowed aria-disabled:opacity-60';

function StatusIcon({ view }: { view: RadioView }) {
  if (view.error !== null) {
    return <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />;
  }
  if (view.status === 'starting' || view.status === 'ending') {
    return <Loader2 className="h-4 w-4 text-primary motion-safe:animate-spin" aria-hidden="true" />;
  }
  if (view.status === 'paused') {
    return <Pause className="h-4 w-4 text-primary" aria-hidden="true" />;
  }
  return (
    <Radio
      className={cn(
        'h-4 w-4 text-primary',
        view.status === 'playing' && 'motion-safe:animate-pulse'
      )}
      aria-hidden="true"
    />
  );
}

/** How often the minutes left are recomputed (they are shown in whole minutes). */
const CLOCK_TICK_MS = 15_000;

/** The current instant, kept in state and refreshed while a timer runs. */
function useNow(running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
    return () => window.clearInterval(timer);
  }, [running]);
  return now;
}

/** The station: its name, where it stands and what airs — the one part announced. */
function Station({ lng, view, name, compact = false }: {
  lng: Language;
  view: RadioView;
  name: string;
  compact?: boolean;
}) {
  const { t } = useTranslation(lng);
  const message = radioStatusMessage(view, lng);
  const airing = airingSegment(view);
  return (
    <div className={cn('flex min-w-0 flex-1 items-center gap-3', compact && 'gap-2')}>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-background/80 ring-1 ring-primary/25">
        <StatusIcon view={view} />
      </span>
      <div role="status" className="min-w-0">
        {/* Live, the line holds still on one line; once the session is over it says
            in full why — a refusal ends on when the radio may play again. */}
        <p className={view.status === 'ended' ? 'break-words' : 'truncate'}>
          <span className="font-semibold">{name}</span>
          <span aria-hidden="true"> · </span>
          <span className="text-xs font-medium uppercase tracking-wide">
            {t(message.key, message.values)}
          </span>
        </p>
        {/* The line stays while the station is live — empty between two
            programmes — so the bar never changes height under the listener's
            finger on a pause or when a programme ends. */}
        {view.status !== 'ended' && (
          <p className={cn('min-h-5 truncate text-sm', compact && 'min-h-0 text-xs')}>
            {airing !== null && (
              <>
                <span className="font-medium">{t(`radio.formats.${airing.format}`)}</span>
                <span aria-hidden="true"> — </span>
                {airing.title}
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * The minutes left, the cost so far and what the planned listening will cost.
 * Each figure is named for a screen reader by visually hidden TEXT: an
 * `aria-label` on a plain `<span>` is prohibited by ARIA 1.2 and read by no
 * screen reader, which would say « €0.0042 » with nothing to say what it is.
 */
function Meters({ lng, view }: { lng: Language; view: RadioView }) {
  const { t } = useTranslation(lng);
  const timed = view.stopAt !== null && view.status !== 'ended';
  const now = useNow(timed);
  const left = timed ? minutesLeft(view.stopAt, now) : null;
  const cost = radioCost(view.costEur, lng);
  const estimate = radioEstimateMessage(view, lng);
  if (left === null && cost === null) return null;
  return (
    // `text-foreground`, never `muted-foreground`: on the bar's tinted ground
    // the muted token measures 4.28:1 (axe, 2026-09-26) — under the 4.5:1 floor.
    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-foreground tabular-nums md:flex-col md:items-end md:gap-y-0.5">
      {left !== null && (
        <span className="inline-flex items-center gap-1.5">
          <Timer className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          {t('radio.banner.minutes_left', { count: left })}
        </span>
      )}
      {cost !== null && (
        <span className="inline-flex items-center gap-1.5">
          <Coins className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          <span>
            <span className="sr-only">{t('radio.banner.cost_label')} </span>
            {cost}
          </span>
          {estimate !== null && (
            <span>
              <span aria-hidden="true">· </span>
              <span className="sr-only">{t('radio.banner.estimate_label')} </span>
              {t(estimate.key, estimate.values)}
            </span>
          )}
        </span>
      )}
    </div>
  );
}

/**
 * One of several labels (icon and words) sharing a place: all of them lay out,
 * so the place is as wide as the longest and each is centred in it; only the
 * one shown is visible and named.
 */
function StackedLabel({ shown, children }: { shown: boolean; children: ReactNode }) {
  return (
    <span
      className={cn(
        'col-start-1 row-start-1 inline-flex items-center justify-center gap-1.5',
        !shown && 'invisible'
      )}
      aria-hidden={!shown || undefined}
    >
      {children}
    </span>
  );
}

function PauseAction({
  lng,
  compact,
  paused,
  pausable,
}: {
  lng: Language;
  compact: boolean;
  paused: boolean;
  pausable: boolean;
}) {
  const { t } = useTranslation(lng);
  const label = t(paused ? 'radio.banner.resume' : 'radio.banner.pause');
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      className={cn(compact ? 'h-9 w-9 p-0' : 'w-full', INERT)}
      aria-disabled={!pausable || undefined}
      aria-label={compact ? label : undefined}
      title={compact ? label : undefined}
      onClick={() => {
        if (!pausable) return;
        const player = radioPlayer();
        if (paused) void player.resume();
        else player.pause();
      }}
    >
      {/* Both labels hold the width: a pause never resizes the controls, so a
          second click meant to resume cannot land on stop. */}
      <span className="grid">
        <StackedLabel shown={!paused}>
          <Pause aria-hidden="true" />
          {!compact && t('radio.banner.pause')}
        </StackedLabel>
        <StackedLabel shown={paused}>
          <Play aria-hidden="true" />
          {!compact && t('radio.banner.resume')}
        </StackedLabel>
      </span>
    </Button>
  );
}

function StopAction({
  lng,
  compact,
  ending,
  onStop,
}: {
  lng: Language;
  compact: boolean;
  ending: boolean;
  onStop: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <Button
      type="button"
      size="sm"
      variant="destructive"
      className={cn(compact ? 'h-9 w-9 p-0' : 'w-full gap-1.5', INERT)}
      aria-disabled={ending || undefined}
      aria-label={compact ? t('radio.banner.stop') : undefined}
      title={compact ? t('radio.banner.stop') : undefined}
      onClick={() => {
        if (!ending) onStop();
      }}
    >
      <Square aria-hidden="true" />
      {!compact && t('radio.banner.stop')}
    </Button>
  );
}

function LiveActions({
  lng,
  view,
  onStop,
  compact = false,
}: {
  lng: Language;
  view: RadioView;
  onStop: () => void;
  compact?: boolean;
}) {
  const paused = view.status === 'paused';
  // Tuning in or signing off, there is nothing to pause: the control stays where
  // it will be, inert — never removed, never `disabled` under a finger (it would
  // blur and leave the tab order).
  const pausable = view.status === 'playing' || view.status === 'waiting' || paused;
  const ending = view.status === 'ending';
  return (
    <div className={cn('grid grid-cols-2', compact ? 'shrink-0 gap-1' : 'gap-2')}>
      <PauseAction lng={lng} compact={compact} paused={paused} pausable={pausable} />
      <StopAction lng={lng} compact={compact} ending={ending} onStop={onStop} />
    </div>
  );
}

function EndedActions({
  lng,
  onDismiss,
  restartRef,
}: {
  lng: Language;
  onDismiss: () => void;
  restartRef: Ref<HTMLButtonElement>;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex items-center gap-2">
      <Button
        ref={restartRef}
        type="button"
        size="sm"
        variant="outline"
        className="gap-1.5"
        onClick={() => void radioPlayer().start()}
      >
        <RotateCcw aria-hidden="true" />
        {t('radio.banner.restart')}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={onDismiss}
        aria-label={t('radio.banner.dismiss')}
        title={t('radio.banner.dismiss')}
      >
        <X aria-hidden="true" />
      </Button>
    </div>
  );
}

export function RadioBanner({ lng, onDismiss }: { lng: Language; onDismiss: () => void }) {
  const { t } = useTranslation(lng);
  const view = useRadioStore(state => state.view);
  const [compact, setCompact] = useState(false);
  const name = view.stationName ?? t('radio.station_name');
  useRadioMediaSession(view.current?.title ?? null, name);
  const warning = view.error !== null;
  const ended = view.status === 'ended';
  // Stopping takes the stop button away with the live controls: a keyboard
  // user would be left on the page's body. Once the stop THEY pressed has ended
  // the session, the focus goes to what replaced it — never when the session
  // ended by itself, nor once they moved the focus elsewhere.
  const stopPressed = useRef(false);
  const restartRef = useRef<HTMLButtonElement>(null);
  const expandRef = useRef<HTMLButtonElement>(null);
  const collapseRef = useRef<HTMLButtonElement>(null);
  const focusAfterToggle = useRef<'expand' | 'collapse' | null>(null);
  useEffect(() => {
    if (focusAfterToggle.current === null) return;
    (compact ? expandRef : collapseRef).current?.focus();
    focusAfterToggle.current = null;
  }, [compact]);
  useEffect(() => {
    if (!ended || !stopPressed.current) return;
    stopPressed.current = false;
    if (document.activeElement === document.body) restartRef.current?.focus();
  }, [ended]);
  const stop = () => {
    stopPressed.current = true;
    void radioPlayer().stop();
  };
  return (
    <section
      aria-label={name}
      className={cn(
        'relative rounded-lg border border-l-4 px-3 py-2 text-sm text-foreground',
        warning
          ? 'border-warning/40 border-l-warning bg-warning/10'
          : 'border-primary/30 border-l-primary bg-primary/10'
      )}
    >
      {compact && !ended && (
        <div className="flex items-center gap-1 md:hidden">
          <Station lng={lng} view={view} name={name} compact />
          <LiveActions lng={lng} view={view} onStop={stop} compact />
          <Button
            ref={expandRef}
            type="button"
            size="sm"
            variant="ghost"
            className="h-9 w-9 shrink-0 p-0"
            aria-label={t('radio.banner.expand')}
            title={t('radio.banner.expand')}
            onClick={() => {
              focusAfterToggle.current = 'collapse';
              setCompact(false);
            }}
          >
            <ChevronDown aria-hidden="true" />
          </Button>
        </div>
      )}
      <div
        className={cn(
          'flex flex-col gap-2 md:flex-row md:items-center md:gap-4',
          compact && !ended && 'hidden md:flex'
        )}
      >
        <Station lng={lng} view={view} name={name} />
        <Meters lng={lng} view={view} />
        {/* On a phone the actions stack: the page's link on the meters' edge,
            then pause and stop as two equal halves of the bar's width. */}
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-end">
          <Button
            asChild
            size="sm"
            variant="ghost"
            className="gap-1.5 self-start px-0 text-primary md:self-auto md:px-3"
          >
            <Link href={buildLocalizedPath('/dashboard/radio', lng)}>
              <FileText aria-hidden="true" />
              {t('radio.banner.open')}
            </Link>
          </Button>
          {ended ? (
            <EndedActions lng={lng} onDismiss={onDismiss} restartRef={restartRef} />
          ) : (
            <LiveActions lng={lng} view={view} onStop={stop} />
          )}
        </div>
      </div>
      {!ended && (
        <Button
          ref={collapseRef}
          type="button"
          size="sm"
          variant="ghost"
          className={cn('absolute right-2 top-2 h-9 w-9 p-0 md:hidden', compact && 'hidden')}
          aria-label={t('radio.banner.collapse')}
          title={t('radio.banner.collapse')}
          onClick={() => {
            focusAfterToggle.current = 'expand';
            setCompact(true);
          }}
        >
          <ChevronUp aria-hidden="true" />
        </Button>
      )}
    </section>
  );
}

/** The bar's height, published for the full-height pages under it (the chat). */
export const RADIO_BANNER_HEIGHT_VAR = '--radio-banner-h';

/**
 * The bar's place under the header: shown while a session runs, and its end
 * until dismissed. A dismissal holds for THAT view — the store publishes a new
 * one at the next start, which shows the bar again (a second failed start
 * included).
 */
export function RadioBannerSlot({ lng }: { lng: Language }) {
  const view = useRadioStore(state => state.view);
  const [dismissed, setDismissed] = useState<RadioView | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const visible = view.status !== 'idle' && view !== dismissed;

  useEffect(() => {
    const element = wrapperRef.current;
    const root = document.documentElement;
    // jsdom has no ResizeObserver; the variable then stays unset, which is the
    // same as absent — the chat shell's fallback is `0px`.
    if (!visible || !element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      root.style.setProperty(RADIO_BANNER_HEIGHT_VAR, `${element.offsetHeight}px`);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      // The bar leaves: the height it claimed goes with it.
      root.style.removeProperty(RADIO_BANNER_HEIGHT_VAR);
    };
  }, [visible]);

  if (!visible) return null;
  return (
    // The gap under the bar is the wrapper's PADDING, never the bar's margin:
    // a margin collapses out of the box whose height is published.
    <div
      ref={wrapperRef}
      className="sticky z-40 rounded-lg bg-background pb-3"
      style={{ top: 'calc(4rem + var(--meeting-banner-h, 0px))' }}
    >
      <RadioBanner lng={lng} onDismiss={() => setDismissed(view)} />
    </div>
  );
}

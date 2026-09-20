'use client';

/**
 * "You are talking with LIA" — a band above the thread (ADR-299, spec A11),
 * on the `ActiveCallBanner` model: a status line outside the exclusive
 * surface slot, gone the moment the session ends. It draws the store; the
 * session it is handed does the work.
 *
 * Controls, every one named and 44 px tall: the microphone toggle, the
 * captions fold (an icon, like its neighbours — owner request 2026-09-19),
 * End, and —
 * while a delegation runs — Stop, which cancels LIA's current turn AND ends
 * the session (the one door that kills a turn).
 *
 * An ending the person did not choose is told once as a toast — a failed
 * start names the API's reason — and the outcome is acknowledged so a later
 * mount does not repeat it.
 *
 * Under the last caption, set off by a lateral bar, the meter (ADR-300 wave
 * 3, owner placement 2026-09-19): what the session is costing the person on
 * their own key, indicative.
 *
 * A DIRECT session (ADR-300 wave 4, ADR-301) carries a notice under its
 * status line: LIA reads for the person and acts on nothing while they
 * talk, and at the end what they asked is relayed to their conversation as
 * a message from them — which the API makes true by construction (no turn
 * archived, the transcript kept and relayed at the closing).
 */
import {
  AudioLines,
  Captions,
  CaptionsOff,
  Forward,
  Mic,
  MicOff,
  PhoneOff,
  Square,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import type { UseLiveSessionReturn } from '@/hooks/useLiveSession';
import { liveErrorKey } from '@/lib/live/live-message';
import type { LiveOutcome } from '@/lib/live/types';
import { cn } from '@/lib/utils';
import { useLiveStore } from '@/stores/liveStore';

import { LiveCaptions } from './LiveCaptions';
import { LiveExtendDialog } from './LiveExtendDialog';
import { LiveMeter } from './LiveMeter';
import { describeVendorBill } from '@/lib/live/vendor-bill-view';

export interface LiveBannerProps {
  session: UseLiveSessionReturn;
  /** Cancel LIA's current turn, then end the session. */
  onStopAll: () => void;
}

/** Endings the person did not choose and cannot read in the thread's card alone. */
const TOLD_OUTCOMES = new Set<LiveOutcome>([
  'provider_closed',
  'resumption_failed',
  'superseded',
  'budget_reached',
]);

/**
 * The session greets its own opening (owner decision 2026-09-19: like the
 * spoken replies, the live entry answers with an active icon and a toast) —
 * on the `live` status, once per session, because the menu's click is a
 * request and the session opens a second later, or not at all.
 */
function useStartedToast(): void {
  const { t } = useTranslation();
  const status = useLiveStore(state => state.status);
  const sessionId = useLiveStore(state => state.sessionId);
  const greeted = useRef<string | null>(null);
  useEffect(() => {
    // Keyed on the session, not on a flag: a reconnection keeps its id and is
    // not greeted again, a new session is — whatever renders were batched.
    if (status !== 'live' || sessionId === null || greeted.current === sessionId) return;
    greeted.current = sessionId;
    toast.success(t('live.toast.started'));
  }, [status, sessionId, t]);
}

/**
 * One toast per ending worth telling, then the outcome is acknowledged. A
 * close the PROVIDER decided carries its own word (the code and reason the
 * API's log also gets), so a session that died in five seconds is not left
 * unexplained on the screen either (owner request 2026-09-19).
 */
function useOutcomeToast(): void {
  const { t } = useTranslation();
  const outcome = useLiveStore(state => state.outcome);
  const error = useLiveStore(state => state.error);
  const detail = useLiveStore(state => state.detail);
  useEffect(() => {
    if (outcome === null) return;
    if (outcome === 'error') toast.error(t(liveErrorKey(error)));
    else if (outcome === 'mic_denied') toast.error(t('live.outcome.mic_denied'));
    else if (TOLD_OUTCOMES.has(outcome)) {
      const why = outcome === 'provider_closed' && detail ? ` — ${detail}` : '';
      toast.info(`${t('live.captions.title')} · ${t(`live.outcome.${outcome}`)}${why}`);
    }
    useLiveStore.getState().acknowledge();
  }, [outcome, error, detail, t]);
}

/**
 * The vendor's own bill of the session that just ended, told once (owner
 * request 2026-09-20: reliable figures, read from the vendor, never
 * recorded): the total in USD, the LLM's and the call's shares in credits
 * when stated, the voice model and the LLM the vendor charged for.
 */
function useVendorBillToast(): void {
  const { t, i18n } = useTranslation();
  const bill = useLiveStore(state => state.vendorBill);
  useEffect(() => {
    if (bill === null) return;
    toast.info(describeVendorBill(bill, t, i18n.language), { duration: 12_000 });
    useLiveStore.getState().setVendorBill(null);
  }, [bill, t, i18n.language]);
}

function MicrophoneControl({ session }: { session: UseLiveSessionReturn }) {
  const { t } = useTranslation();
  const muted = useLiveStore(state => state.muted);
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={session.toggleMute}
      aria-pressed={muted}
      aria-label={muted ? t('live.mic.unmute') : t('live.mic.mute')}
      title={muted ? t('live.mic.unmute') : t('live.mic.mute')}
      className="min-h-11 min-w-11"
    >
      {muted ? (
        <MicOff className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Mic className="h-4 w-4" aria-hidden="true" />
      )}
    </Button>
  );
}

export function LiveBanner({ session, onStopAll }: LiveBannerProps) {
  const { t } = useTranslation();
  const status = useLiveStore(state => state.status);
  const captions = useLiveStore(state => state.captions);
  const delegating = useLiveStore(state => state.delegating);
  const direct = useLiveStore(state => state.mode === 'direct');
  const timeLeftMs = useLiveStore(state => state.timeLeftMs);
  const idleCountdown = useLiveStore(state => state.idleCountdownSeconds);
  const [expanded, setExpanded] = useState(false);
  useOutcomeToast();
  useVendorBillToast();
  useStartedToast();

  if (status === 'idle' || status === 'ended') return null;

  // A direct session (ADR-300 wave 4) runs no chat turn: its wait is a
  // lookup, named as such, and there is nothing to stop.
  const workingKey = direct ? 'live.status.looking_up' : 'live.status.delegating';
  const statusKey = delegating ? workingKey : `live.status.${status}`;
  return (
    <section
      aria-label={t('live.captions.title')}
      data-testid="live-banner"
      // An opaque base under the tint: the band sits in the sticky top block and
      // the thread scrolls beneath it (owner report 2026-09-18: the text showed
      // through). One element: `bg-card` paints the colour, the gradient the tint.
      className="flex flex-col gap-1 border-b border-primary/25 bg-card bg-gradient-to-r from-primary/10 to-primary/10 px-4 py-2 text-xs"
    >
      <div className="flex flex-wrap items-center gap-2">
        <AudioLines
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-primary',
            status === 'live' && 'motion-safe:animate-pulse'
          )}
          aria-hidden="true"
        />
        <span className="font-semibold text-primary" role="status">
          {direct && `${t('live.status.direct')} · `}
          {t(statusKey)}
          {timeLeftMs !== null &&
            ` · ${t('live.status.time_left', { count: Math.ceil(timeLeftMs / 1000) })}`}
          {idleCountdown !== null &&
            ` · ${t('live.status.idle_countdown', { count: idleCountdown })}`}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setExpanded(value => !value)}
            aria-expanded={expanded}
            aria-label={expanded ? t('live.captions.hide') : t('live.captions.show')}
            title={expanded ? t('live.captions.hide') : t('live.captions.show')}
            className="min-h-11 min-w-11 text-muted-foreground"
          >
            {expanded ? (
              <CaptionsOff className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Captions className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
          <MicrophoneControl session={session} />
          {delegating && !direct && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onStopAll}
              aria-label={t('live.button.stop_all')}
              title={t('live.button.stop_all')}
              className="min-h-11 min-w-11 text-destructive"
            >
              <Square className="h-4 w-4" aria-hidden="true" />
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => void session.end('ended')}
            aria-label={t('live.button.end')}
            title={t('live.button.end')}
            className="min-h-11 min-w-11"
          >
            <PhoneOff className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
      {direct && (
        <p
          role="note"
          data-testid="live-direct-notice"
          className="flex items-start gap-1.5 text-muted-foreground"
        >
          <Forward className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{t('live.direct_notice')}</span>
        </p>
      )}
      <LiveCaptions captions={captions} expanded={expanded} />
      <LiveMeter />
      <LiveExtendDialog session={session} />
    </section>
  );
}

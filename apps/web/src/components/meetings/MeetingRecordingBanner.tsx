'use client';

/**
 * The recording's presence on screen (ADR-258).
 *
 * A recording that cannot be seen cannot be stopped: whatever page of the
 * dashboard the user is on, this bar says a capture is open, for how long,
 * whether its segments are leaving, and offers the one or two actions the
 * phase allows. It also carries the silence prompt ("still recording?") and
 * the two recoveries — resume/finalize/discard after an interruption, finalize
 * anyway when segments never reached the server.
 *
 * Native controls only, every name translated, `role="status"` so a screen
 * reader hears the phase change without being interrupted. Split into small
 * components by concern (CC discipline): the status line, the actions, the
 * notices, the silence prompt.
 */

import { AlertTriangle, Check, CircleDot, Loader2, Play, Square, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { MEETING_DEFAULT_SILENCE_PROMPT_MINUTES } from '@/lib/constants';
import { formatElapsed, isBannerPhase } from '@/lib/meetings/format';
import type { MeetingRecorderPhase } from '@/stores/meetingRecorderStore';
import { cn } from '@/lib/utils';

interface BannerProps {
  lng: Language;
  recorder: UseMeetingRecorderReturn;
}

const BUSY_PHASES: readonly MeetingRecorderPhase[] = ['starting', 'stopping', 'processing'];
const WARNING_PHASES: readonly MeetingRecorderPhase[] = ['error', 'interrupted', 'offline'];

/** Pending audio above this many minutes while offline earns a warning. */
const OFFLINE_WARNING_MINUTES = 30;

/** Whether the queue holds more than the warning threshold of unsent audio. */
export function isOfflineTooLong(recorder: UseMeetingRecorderReturn): boolean {
  if (recorder.phase !== 'offline' || recorder.recording === null) return false;
  return (
    recorder.pendingSegments * recorder.recording.segmentSeconds >= OFFLINE_WARNING_MINUTES * 60
  );
}

/** Surface tone per phase — one table, not a chain of ternaries in the render. */
function bannerTone(phase: MeetingRecorderPhase): string {
  if (phase === 'error') return 'border-destructive/40 bg-destructive/10';
  if (phase === 'interrupted' || phase === 'offline') return 'border-warning/40 bg-warning/10';
  return 'border-primary/30 bg-primary/10';
}

/** Level meter — decorative (the elapsed time is the information). */
function LevelMeter({ level, label }: { level: number; label: string }) {
  const width = Math.min(100, Math.round(Math.sqrt(level) * 140));
  return (
    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted" role="img" aria-label={label}>
      <div
        className="h-full rounded-full bg-primary transition-[width] duration-150"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

function PhaseIcon({ phase }: { phase: MeetingRecorderPhase }) {
  if (phase === 'recording') {
    return (
      <CircleDot
        className="h-4 w-4 animate-pulse text-destructive"
        aria-hidden="true"
        data-testid="meeting-recording-dot"
      />
    );
  }
  if (BUSY_PHASES.includes(phase)) {
    return <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />;
  }
  if (WARNING_PHASES.includes(phase)) {
    return <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />;
  }
  return null;
}

function StatusLine({ lng, recorder }: BannerProps) {
  const { t } = useTranslation(lng);
  return (
    <>
      <span className="inline-flex items-center gap-2 font-medium">
        <PhaseIcon phase={recorder.phase} />
        {t(`meetings.banner.${recorder.phase}`)}
      </span>
      {recorder.isLive && (
        <span className="tabular-nums" aria-label={t('meetings.banner.elapsed_label')}>
          {formatElapsed(recorder.elapsedSeconds)}
        </span>
      )}
      {recorder.isCapturing && (
        <LevelMeter level={recorder.level} label={t('meetings.banner.level_label')} />
      )}
      {recorder.isLive && (
        <span className="text-xs text-muted-foreground">
          {t('meetings.banner.uploaded', { count: recorder.uploadedSegments })}
          {recorder.pendingSegments > 0 &&
            ` · ${t('meetings.banner.pending', { count: recorder.pendingSegments })}`}
        </span>
      )}
    </>
  );
}

/** The interrupted recoveries: resume (when possible), finalize (with gaps when known). */
function InterruptedActions({ lng, recorder }: BannerProps) {
  const { t } = useTranslation(lng);
  const gaps = recorder.missingSegments !== null;
  return (
    <>
      {!gaps && recorder.isSupported && (
        <Button
          type="button"
          size="sm"
          variant="default"
          onClick={() => void recorder.resume()}
          className="gap-1"
        >
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
          {t('meetings.banner.resume')}
        </Button>
      )}
      <Button
        type="button"
        size="sm"
        variant={gaps ? 'default' : 'outline'}
        onClick={() => void (gaps ? recorder.finalizeWithGaps() : recorder.stop())}
        className="gap-1"
      >
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
        {t(gaps ? 'meetings.banner.finalize_with_gaps' : 'meetings.banner.finalize')}
      </Button>
    </>
  );
}

function Actions({ lng, recorder }: BannerProps) {
  const { t } = useTranslation(lng);
  const { phase } = recorder;
  return (
    <span className="ml-auto inline-flex flex-wrap items-center gap-2">
      {recorder.isCapturing && (
        <Button
          type="button"
          size="sm"
          variant="default"
          onClick={() => void recorder.stop()}
          className="gap-1"
        >
          <Square className="h-3.5 w-3.5" aria-hidden="true" />
          {t('meetings.banner.stop')}
        </Button>
      )}
      {phase === 'interrupted' && <InterruptedActions lng={lng} recorder={recorder} />}
      {recorder.isLive && phase !== 'stopping' && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="gap-1 text-destructive"
          onClick={() => void recorder.discard()}
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          {t('meetings.banner.discard')}
        </Button>
      )}
      {(phase === 'error' || phase === 'processing') && (
        <Button type="button" size="sm" variant="ghost" onClick={recorder.dismiss}>
          {t('meetings.banner.dismiss')}
        </Button>
      )}
    </span>
  );
}

function Notices({ lng, recorder }: BannerProps) {
  const { t } = useTranslation(lng);
  const missing = recorder.missingSegments;
  const code = recorder.errorCode;
  return (
    <>
      {missing !== null && missing.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          {t('meetings.banner.missing_segments', { count: missing.length })}
        </p>
      )}
      {code !== null && (
        <p className="mt-1 text-xs text-destructive">
          {t(`meetings.errors.${code}`, {
            defaultValue: t('meetings.errors.unknown', { code }),
          })}
        </p>
      )}
      {recorder.isCapturing && (
        <p className="mt-1 text-xs text-muted-foreground">{t('meetings.banner.keep_screen_on')}</p>
      )}
      {isOfflineTooLong(recorder) && (
        <p className="mt-1 text-xs text-warning">{t('meetings.banner.offline_long')}</p>
      )}
    </>
  );
}

function SilencePrompt({ lng, recorder }: BannerProps) {
  const { t } = useTranslation(lng);
  return (
    <div
      role="alertdialog"
      aria-labelledby="meeting-silence-title"
      aria-describedby="meeting-silence-body"
      className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-warning/40 bg-background/80 p-2"
    >
      <span id="meeting-silence-title" className="font-medium">
        {t('meetings.banner.silence_title')}
      </span>
      <span id="meeting-silence-body" className="text-xs text-muted-foreground">
        {t('meetings.banner.silence_body', {
          minutes: recorder.limits?.silence_prompt_minutes ?? MEETING_DEFAULT_SILENCE_PROMPT_MINUTES,
        })}
      </span>
      <span className="ml-auto inline-flex gap-2">
        <Button type="button" size="sm" variant="default" onClick={recorder.continueAfterSilence}>
          {t('meetings.banner.silence_continue')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => void recorder.stop()}>
          {t('meetings.banner.stop')}
        </Button>
      </span>
    </div>
  );
}

export function MeetingRecordingBanner({ lng, recorder }: BannerProps) {
  const { t } = useTranslation(lng);
  if (!isBannerPhase(recorder.phase)) return null;
  return (
    <section
      role="status"
      aria-live="polite"
      aria-label={t('meetings.banner.region_label')}
      className={cn(
        'mb-3 rounded-lg border px-3 py-2 text-sm shadow-sm',
        bannerTone(recorder.phase)
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusLine lng={lng} recorder={recorder} />
        <Actions lng={lng} recorder={recorder} />
      </div>
      <Notices lng={lng} recorder={recorder} />
      {recorder.silencePrompt && <SilencePrompt lng={lng} recorder={recorder} />}
    </section>
  );
}

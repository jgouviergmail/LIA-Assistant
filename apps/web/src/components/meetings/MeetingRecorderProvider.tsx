'use client';

/**
 * Owner of the meeting recorder for the whole dashboard (ADR-258).
 *
 * Mounted once in the dashboard layout so a recording survives navigation; the
 * composer asks it to start, the banner it renders asks it to stop. Without a
 * provider (unit tests of the composer, pages outside the dashboard) the
 * context is `null` and consumers hide the feature.
 */

import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { toast } from 'sonner';

import { MeetingRecordingBanner } from '@/components/meetings/MeetingRecordingBanner';
import { useMeetingRecorder, type UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MeetingDetail } from '@/types/meetings';

/**
 * What the rest of the dashboard sees of the recorder.
 *
 * The fine-grained fields — level meter, elapsed seconds, upload counters —
 * change several times a second while recording and belong to the banner,
 * which reads the hook directly. Publishing them through the context would
 * re-render every consumer (the composer among them) at that cadence for the
 * whole meeting; the context therefore carries the coarse state and the
 * commands only, and changes when THEY change.
 */
export type MeetingRecorderContextValue = Omit<
  UseMeetingRecorderReturn,
  'level' | 'elapsedSeconds' | 'uploadedSegments' | 'pendingSegments'
>;

const MeetingRecorderContext = createContext<MeetingRecorderContextValue | null>(null);

/** The recorder, or `null` outside the dashboard (the composer then hides the entry). */
export function useMeetingRecorderContext(): MeetingRecorderContextValue | null {
  return useContext(MeetingRecorderContext);
}

interface MeetingRecorderProviderProps {
  lng: Language;
  /** The instance flag: a disabled feature mounts nothing and starts nothing. */
  enabled: boolean;
  children: ReactNode;
}

function RecorderShell({ lng, children }: { lng: Language; children: ReactNode }) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();

  const onProcessed = useCallback(
    (detail: MeetingDetail) => {
      const title = detail.report?.title ?? t('meetings.list.untitled');
      if (detail.status === 'ready') {
        toast.success(t('meetings.toasts.ready_title'), {
          description: title,
          action: {
            label: t('meetings.banner.open_minutes'),
            onClick: () => router.push(`/dashboard/meetings/${detail.id}`),
          },
        });
      } else {
        toast.error(t('meetings.toasts.failed_title'), {
          description: detail.last_error_code
            ? t(`meetings.errors.${detail.last_error_code}`, {
                defaultValue: t('meetings.errors.unknown', { code: detail.last_error_code }),
              })
            : undefined,
          action: {
            label: t('meetings.banner.open_minutes'),
            onClick: () => router.push(`/dashboard/meetings/${detail.id}`),
          },
        });
      }
    },
    [router, t]
  );

  const recorder = useMeetingRecorder(onProcessed);
  const {
    phase,
    recording,
    engine,
    limits,
    silencePrompt,
    errorCode,
    missingSegments,
    isSupported,
    isCapturing,
    isLive,
    start,
    stop,
    finalizeWithGaps,
    resume,
    discard,
    dismiss,
    continueAfterSilence,
  } = recorder;
  const contextValue = useMemo<MeetingRecorderContextValue>(
    () => ({
      phase,
      recording,
      engine,
      limits,
      silencePrompt,
      errorCode,
      missingSegments,
      isSupported,
      isCapturing,
      isLive,
      start,
      stop,
      finalizeWithGaps,
      resume,
      discard,
      dismiss,
      continueAfterSilence,
    }),
    [
      phase,
      recording,
      engine,
      limits,
      silencePrompt,
      errorCode,
      missingSegments,
      isSupported,
      isCapturing,
      isLive,
      start,
      stop,
      finalizeWithGaps,
      resume,
      discard,
      dismiss,
      continueAfterSilence,
    ]
  );

  return (
    <MeetingRecorderContext.Provider value={contextValue}>
      <MeetingRecordingBanner lng={lng} recorder={recorder} />
      {children}
    </MeetingRecorderContext.Provider>
  );
}

export function MeetingRecorderProvider({ lng, enabled, children }: MeetingRecorderProviderProps) {
  if (!enabled) return <>{children}</>;
  return <RecorderShell lng={lng}>{children}</RecorderShell>;
}

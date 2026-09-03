'use client';

/**
 * Owner of the meeting recorder for the whole dashboard (ADR-258, ADR-259).
 *
 * Mounted once in the dashboard layout, ABOVE the header, so a recording
 * survives navigation and the header's controls (the desktop toggle, the logo
 * menu on a phone) can read it. The banner is not rendered here: it goes where
 * `MeetingRecorderBannerSlot` is placed — at the top of the page content, sticky
 * under the header — because a recording that cannot be seen cannot be stopped.
 * Without a provider (unit tests of the composer, pages outside the dashboard)
 * the context is `null` and consumers hide the feature.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';
import { toast } from 'sonner';

import { MeetingRecordingBanner } from '@/components/meetings/MeetingRecordingBanner';
import { useMeetingRecorder, type UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isBannerPhase } from '@/lib/meetings/format';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import type { MeetingDetail } from '@/types/meetings';

/**
 * What the rest of the dashboard sees of the recorder.
 *
 * The fine-grained fields — level meter, elapsed seconds, upload counters —
 * change several times a second while recording and belong to the banner,
 * which reads the store directly. Publishing them through the context would
 * re-render every consumer (the composer among them) at that cadence for the
 * whole meeting; the context therefore carries the coarse state and the
 * commands only, and changes when THEY change.
 */
export type MeetingRecorderContextValue = Omit<
  UseMeetingRecorderReturn,
  'level' | 'elapsedSeconds' | 'uploadedSegments' | 'pendingSegments'
>;

const MeetingRecorderContext = createContext<MeetingRecorderContextValue | null>(null);

/**
 * The CSS custom property carrying the banner's measured height.
 *
 * The chat shell is locked to the dynamic viewport minus the chrome above it
 * and subtracts this variable (next to the connector banner's): a banner
 * inserted in that flow without telling it pushed the composer below the fold
 * for the whole recording (measured 2026-09-03). The `0px` fallback on the
 * consumer side keeps its arithmetic unchanged while no banner is mounted.
 */
export const MEETING_BANNER_HEIGHT_VAR = '--meeting-banner-h';

/** The recorder, or `null` outside the dashboard (consumers then hide the entry). */
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
      {children}
    </MeetingRecorderContext.Provider>
  );
}

export function MeetingRecorderProvider({ lng, enabled, children }: MeetingRecorderProviderProps) {
  if (!enabled) return <>{children}</>;
  return <RecorderShell lng={lng}>{children}</RecorderShell>;
}

/**
 * Where the banner renders: sticky under the header, publishing its height.
 *
 * The ONE consumer allowed to read the fine-grained store (level, elapsed,
 * counters): it owns the banner. Renders nothing outside a provider or while
 * there is nothing to say (`isBannerPhase`).
 */
export function MeetingRecorderBannerSlot({ lng }: { lng: Language }) {
  const context = useMeetingRecorderContext();
  const state = useMeetingRecorderStore();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const visible = context !== null && isBannerPhase(state.phase);

  useEffect(() => {
    const element = wrapperRef.current;
    const root = document.documentElement;
    // jsdom has no ResizeObserver; the variable then stays unset, which is
    // the same as absent — the consumers' fallback is `0px`.
    if (!visible || !element || typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(() => {
      root.style.setProperty(MEETING_BANNER_HEIGHT_VAR, `${element.offsetHeight}px`);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      // The banner leaves: the height it claimed must go with it.
      root.style.removeProperty(MEETING_BANNER_HEIGHT_VAR);
    };
  }, [visible]);

  if (context === null || !visible) return null;
  const recorder: UseMeetingRecorderReturn = {
    ...context,
    level: state.level,
    elapsedSeconds: state.elapsedSeconds,
    uploadedSegments: state.uploadedSegments,
    pendingSegments: state.pendingSegments,
  };
  return (
    <div ref={wrapperRef} className="sticky top-16 z-40 rounded-lg bg-background">
      <MeetingRecordingBanner lng={lng} recorder={recorder} />
    </div>
  );
}

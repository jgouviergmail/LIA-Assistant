'use client';

/**
 * The actions of the meeting page (ADR-258), out of the render hotspot.
 *
 * Every confirmed action asks through the shared confirm dialog, maps a
 * server refusal to its localized sentence (stable `detail.code`) and updates
 * the local draft the page owns. The page only wires buttons to these.
 */

import { useCallback, type Dispatch, type SetStateAction } from 'react';
import { toast } from 'sonner';

import type { ConfirmOptions } from '@/components/ui/use-confirm';
import type { UseMeetingReturn } from '@/hooks/useMeetings';
import { meetingErrorCode } from '@/lib/meetings/api';
import type { MeetingReport } from '@/types/meetings';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface MeetingActionDeps {
  t: Translate;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  navigateToList: () => void;
  setDraft: Dispatch<SetStateAction<MeetingReport | null>>;
  setShowTranscript: Dispatch<SetStateAction<boolean>>;
}

export interface MeetingActions {
  save: (draft: MeetingReport) => Promise<void>;
  resetReport: () => Promise<void>;
  regenerate: () => Promise<void>;
  retry: () => Promise<void>;
  email: () => Promise<void>;
  deleteTranscript: () => Promise<void>;
  remove: () => Promise<void>;
}

/** A server refusal as the user reads it, or the fallback. */
export function describeFailure(t: Translate, error: unknown, fallbackKey: string): string {
  const code = meetingErrorCode(error);
  return code
    ? t(`meetings.errors.${code}`, { defaultValue: t('meetings.errors.unknown', { code }) })
    : t(fallbackKey);
}

export function useMeetingActions(
  state: UseMeetingReturn,
  deps: MeetingActionDeps
): MeetingActions {
  const { t, confirm, navigateToList, setDraft, setShowTranscript } = deps;

  const run = useCallback(
    async (operation: () => Promise<void>, successKey?: string) => {
      try {
        await operation();
        if (successKey) toast.success(t(successKey));
      } catch (error) {
        toast.error(describeFailure(t, error, 'common.error'));
      }
    },
    [t]
  );

  const confirmed = useCallback(
    async (prefix: string, confirmLabelKey: string, destructive: boolean) =>
      confirm({
        title: t(`meetings.detail.${prefix}_title`),
        description: t(`meetings.detail.${prefix}_description`),
        confirmLabel: t(confirmLabelKey),
        destructive,
      }),
    [confirm, t]
  );

  const save = useCallback(
    (draft: MeetingReport) =>
      run(async () => {
        await state.patch({
          title: draft.title,
          participants: draft.participants,
          sections: draft.sections,
        });
        setDraft(null);
      }, 'meetings.detail.saved'),
    [run, setDraft, state]
  );

  const resetReport = useCallback(async () => {
    if (!(await confirmed('confirm_reset', 'meetings.detail.reset', false))) return;
    await run(async () => {
      await state.resetReport();
      setDraft(null);
    }, 'meetings.detail.saved');
  }, [confirmed, run, setDraft, state]);

  const regenerate = useCallback(async () => {
    if (!(await confirmed('confirm_regenerate', 'meetings.detail.regenerate', false))) return;
    await run(async () => {
      await state.regenerate();
      setDraft(null);
    });
  }, [confirmed, run, setDraft, state]);

  const retry = useCallback(() => run(() => state.retry()), [run, state]);

  const email = useCallback(
    () =>
      run(async () => {
        await state.email();
      }, 'meetings.detail.email_ok'),
    [run, state]
  );

  const deleteTranscript = useCallback(async () => {
    if (
      !(await confirmed('confirm_delete_transcript', 'meetings.detail.delete_transcript', true))
    ) {
      return;
    }
    await run(async () => {
      await state.deleteTranscript();
      setShowTranscript(false);
    });
  }, [confirmed, run, setShowTranscript, state]);

  const remove = useCallback(async () => {
    if (!(await confirmed('confirm_delete', 'meetings.detail.delete', true))) return;
    await run(async () => {
      if (await state.remove()) {
        toast.success(t('meetings.detail.deleted'));
        navigateToList();
      }
    });
  }, [confirmed, navigateToList, run, state, t]);

  return { save, resetReport, regenerate, retry, email, deleteTranscript, remove };
}

'use client';

/**
 * The actions of the meeting page (ADR-258), out of the render hotspot.
 *
 * Every confirmed action asks through the shared confirm dialog, maps a
 * server refusal to its localized sentence (stable `detail.code`) and updates
 * the local draft the page owns. The page only wires buttons to these.
 */

import { useCallback, type Dispatch, type SetStateAction } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';

import type { ConfirmOptions } from '@/components/ui/use-confirm';
import type { UseMeetingReturn } from '@/hooks/useMeetings';
import { meetingErrorCode } from '@/lib/meetings/api';
import type { MeetingReformatRequest, MeetingReport } from '@/types/meetings';

export type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface MeetingActionDeps {
  t: Translate;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  navigateToList: () => void;
  /** Where new minutes written from this transcript live (reformat `new`). */
  navigateToMeeting: (id: string) => void;
  setDraft: Dispatch<SetStateAction<MeetingReport | null>>;
  setShowTranscript: Dispatch<SetStateAction<boolean>>;
}

export interface MeetingActions {
  save: (draft: MeetingReport) => Promise<void>;
  resetReport: () => Promise<void>;
  regenerate: () => Promise<void>;
  /** Write the minutes again with another template, in place or as new minutes. */
  reformat: (request: MeetingReformatRequest) => Promise<void>;
  retry: () => Promise<void>;
  email: () => Promise<void>;
  deleteTranscript: () => Promise<void>;
  remove: () => Promise<void>;
}

/** The user-facing sentence behind a stable meeting error code (unknown codes stay readable). */
export function meetingErrorLabel(t: Translate, code: string): string {
  return t(`meetings.errors.${code}`, { defaultValue: t('meetings.errors.unknown', { code }) });
}

/** A server refusal as the user reads it, or the fallback. */
export function describeFailure(t: Translate, error: unknown, fallbackKey: string): string {
  const code = meetingErrorCode(error);
  return code ? meetingErrorLabel(t, code) : t(fallbackKey);
}

export function useMeetingActions(
  state: UseMeetingReturn,
  deps: MeetingActionDeps
): MeetingActions {
  const { t, confirm, navigateToList, navigateToMeeting, setDraft, setShowTranscript } = deps;
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const toast = useApplicationAccountToast(user?.id);

  const run = useCallback(
    async (operation: () => Promise<void | boolean>, successKey?: string) => {
      if (!isCurrent()) return;
      try {
        const outcome = await operation();
        if (outcome !== false && isCurrent() && successKey) toast.success(t(successKey));
      } catch (error) {
        toast.error(describeFailure(t, error, 'common.error'));
      }
    },
    [t, isCurrent, toast]
  );

  const confirmed = useCallback(
    async (prefix: string, confirmLabelKey: string, destructive: boolean) => {
      if (!isCurrent()) return false;
      const approved = await confirm({
        title: t(`meetings.detail.${prefix}_title`),
        description: t(`meetings.detail.${prefix}_description`),
        confirmLabel: t(confirmLabelKey),
        destructive,
      });
      return approved && isCurrent();
    },
    [confirm, t, isCurrent]
  );

  const save = useCallback(
    (draft: MeetingReport) =>
      run(async () => {
        const saved = await state.patch({
          title: draft.title,
          participants: draft.participants,
          sections: draft.sections,
        });
        if (saved === null || !isCurrent()) return false;
        setDraft(null);
      }, 'meetings.detail.saved'),
    [run, setDraft, state, isCurrent]
  );

  const resetReport = useCallback(async () => {
    if (!(await confirmed('confirm_reset', 'meetings.detail.reset', false))) return;
    await run(async () => {
      const saved = await state.resetReport();
      if (saved === null || !isCurrent()) return false;
      setDraft(null);
    }, 'meetings.detail.saved');
  }, [confirmed, run, setDraft, state, isCurrent]);

  const regenerate = useCallback(async () => {
    if (!(await confirmed('confirm_regenerate', 'meetings.detail.regenerate', false))) return;
    await run(async () => {
      await state.regenerate();
      if (!isCurrent()) return;
      setDraft(null);
    });
  }, [confirmed, run, setDraft, state, isCurrent]);

  const reformat = useCallback(
    (request: MeetingReformatRequest) =>
      run(async () => {
        const response = await state.reformat(request);
        if (response === null || !isCurrent()) return;
        setDraft(null);
        if (request.mode === 'new') {
          toast.success(t('meetings.detail.reformat.started_new'));
          navigateToMeeting(response.id);
        } else {
          toast.success(t('meetings.detail.reformat.started_replace'));
        }
      }),
    [navigateToMeeting, run, setDraft, state, t, isCurrent, toast]
  );

  const retry = useCallback(() => run(() => state.retry()), [run, state]);

  const email = useCallback(
    () =>
      run(async () => {
        return await state.email() !== null;
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
      const saved = await state.deleteTranscript();
      if (saved === null || !isCurrent()) return;
      setShowTranscript(false);
    });
  }, [confirmed, run, setShowTranscript, state, isCurrent]);

  const remove = useCallback(async () => {
    if (!(await confirmed('confirm_delete', 'meetings.detail.delete', true))) return;
    await run(async () => {
      if (await state.remove() && isCurrent()) {
        toast.success(t('meetings.detail.deleted'));
        navigateToList();
      }
    });
  }, [confirmed, navigateToList, run, state, t, isCurrent, toast]);

  return { save, resetReport, regenerate, reformat, retry, email, deleteTranscript, remove };
}

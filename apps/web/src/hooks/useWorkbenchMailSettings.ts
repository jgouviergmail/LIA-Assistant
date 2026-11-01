'use client';

/**
 * Gmail's mailbox settings on the mail screen (ADR-369, Tasks 4.6-4.7): the
 * vacation responder, read and set in the account's own days (the last one
 * included), and the filters, listed and created once per submission. Nothing
 * deletes a filter here: Gmail's client has no such act, and the panel says so.
 * Both are read only while the panel is open.
 */
import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import type { MailFilter, MailVacation } from '@/lib/workbench/types';

const MAIL = '/workbench/mail';

/** The vacation responder set: on with its words and days, or off. */
export interface MailVacationBody {
  enabled: boolean;
  subject?: string;
  body?: string;
  start_date?: string | null;
  end_date?: string | null;
}

/** A filter created: one criterion and one action at least. */
export interface MailFilterBody {
  sender?: string;
  recipient?: string;
  subject?: string;
  query?: string;
  has_attachment?: boolean;
  add_label_id?: string;
  archive?: boolean;
  mark_read?: boolean;
  idempotency_key: string;
}

export interface WorkbenchMailSettings {
  vacation: MailVacation | undefined;
  vacationError: unknown;
  filters: MailFilter[] | undefined;
  filtersError: unknown;
  setVacation: (change: MailVacationBody) => Promise<void>;
  createFilter: (body: MailFilterBody) => Promise<void>;
}

/**
 * @param vacationOffered - Whether the vacation responder is on screen and offered.
 * @param filtersOffered - Whether the filters are.
 */
export function useWorkbenchMailSettings(
  vacationOffered: boolean,
  filtersOffered: boolean
): WorkbenchMailSettings {
  const vacation = useApplicationAccountQuery<MailVacation>(
    `${MAIL}/vacation`,
    'WorkbenchMailSettings',
    vacationOffered
  );
  const filters = useApplicationAccountQuery<{ filters: MailFilter[] }>(
    `${MAIL}/filters`,
    'WorkbenchMailSettings',
    filtersOffered
  );
  const { setData: showVacation } = vacation;
  const { refetch: rereadFilters } = filters;
  const { mutate: put } = useApiMutation<MailVacationBody, MailVacation>({
    method: 'PUT',
    componentName: 'WorkbenchMailSettings',
  });
  const { mutate: post } = useApiMutation<MailFilterBody, MailFilter>({
    method: 'POST',
    componentName: 'WorkbenchMailSettings',
  });

  const setVacation = useCallback(
    async (change: MailVacationBody) => {
      const saved = await put(`${MAIL}/vacation`, change);
      if (saved) showVacation(saved);
    },
    [put, showVacation]
  );

  const createFilter = useCallback(
    async (body: MailFilterBody) => {
      await post(`${MAIL}/filters`, body);
      // The filter exists; a failed re-read is the list's own error, said there.
      await rereadFilters().catch(() => undefined);
    },
    [post, rereadFilters]
  );

  return {
    vacation: vacation.data,
    vacationError: vacation.error,
    filters: filters.data?.filters,
    filtersError: filters.error,
    setVacation,
    createFilter,
  };
}

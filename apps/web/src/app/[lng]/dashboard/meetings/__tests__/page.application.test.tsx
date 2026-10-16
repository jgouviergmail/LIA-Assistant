/** The meetings list with real account lifetimes, reads, selection and confirmation. */
import { type ContextType } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  act,
  answerConfirmDialog,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import { AuthContext, type User } from '@/lib/auth';
import { ApiError } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import type {
  MeetingBulkDeleteResponse,
  MeetingListResponse,
  MeetingSummary,
} from '@/types/meetings';

const { list, bulkDelete, toast, push } = vi.hoisted(() => ({
  list: vi.fn<(limit: number, offset: number) => Promise<MeetingListResponse>>(),
  bulkDelete: vi.fn<(ids: string[]) => Promise<MeetingBulkDeleteResponse>>(),
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
  push: vi.fn(),
}));
vi.mock('@/lib/meetings/api', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/meetings/api')>();
  return { ...original, meetingsApi: { ...original.meetingsApi, list, bulkDelete } };
});
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
vi.mock('@/hooks/useBackOrigin', () => ({ useBackOrigin: () => null }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => null,
}));

import MeetingsPage from '../page';

const params = Promise.resolve({ lng: 'en' });

function session(id: string): NonNullable<ContextType<typeof AuthContext>> {
  const user: User = {
    id,
    email: `${id}@example.test`,
    is_active: true,
    is_verified: true,
    is_superuser: false,
    memory_enabled: true,
    execution_mode: 'pipeline',
    voice_enabled: false,
    voice_mode_enabled: false,
    voice_stt_mode: 'local',
    tokens_display_enabled: false,
    debug_panel_enabled: false,
    response_display_mode: 'streaming',
    onboarding_completed: true,
  };
  return {
    user,
    isLoading: false,
    login: async () => ({ user, mfaRequired: false, mfaToken: null }),
    verifyMfa: async () => user,
    register: async () => user,
    logout: async () => {},
    initiateGoogleOAuth: async () => {},
    completeNativeSignIn: async () => ({ mfaRequired: false }),
    refreshUser: async () => true,
  };
}

function page(owner = 'one') {
  return (
    <AuthContext.Provider value={session(owner)}>
      <MeetingsPage params={params} />
    </AuthContext.Provider>
  );
}

function meeting(id: string, over: Partial<MeetingSummary> = {}): MeetingSummary {
  return {
    id,
    title: id,
    status: 'ready',
    stage: null,
    started_at: '2026-10-15T09:00:00Z',
    stopped_at: '2026-10-15T10:00:00Z',
    audio_duration_seconds: 3600,
    participants_count: 2,
    action_items_count: 1,
    index_state: 'indexed',
    stt_provider: 'local',
    total_cost_eur: null,
    last_error_code: null,
    template_ref: null,
    template_name: null,
    template_selection: null,
    source_meeting_id: null,
    ...over,
  };
}

function response(items: MeetingSummary[], total = items.length, offset = 0): MeetingListResponse {
  return { items, total, limit: 20, offset };
}

function rowBox(title: string) {
  const row = screen.getByText(title).closest('li');
  if (!row) throw new Error('Meeting must belong to a list row');
  return within(row).getByRole('checkbox', { name: 'meetings.list.select_row' });
}

function invalidate(owner = 'one') {
  act(() => publishApplicationResources(owner, new Set(['meetings'])));
}

beforeEach(() => {
  vi.clearAllMocks();
  list.mockReset();
  bulkDelete.mockReset();
  list.mockResolvedValue(response([]));
  bulkDelete.mockResolvedValue({ deleted: [], skipped: [] });
});

describe('meetings list application recovery', () => {
  it('distinguishes a failed initial GET from an empty list and retries the read', async () => {
    list.mockRejectedValueOnce(new ApiError('offline', 500));
    list.mockResolvedValueOnce(response([meeting('Recovered meeting')]));
    const { user } = renderWithProviders(page());

    await screen.findByText('meetings.list.load_error');
    expect(screen.queryByText('meetings.list.empty_title')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    await screen.findByText('Recovered meeting');
    expect(screen.queryByText('meetings.list.load_error')).not.toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('recovers a valid offset when an external mutation empties the last page', async () => {
    list.mockResolvedValueOnce(response([meeting('First page')], 21));
    list.mockResolvedValueOnce(response([meeting('Last page')], 21, 20));
    list.mockResolvedValueOnce(response([], 20, 20));
    list.mockResolvedValueOnce(response([meeting('Remaining meeting')], 20));
    const { user } = renderWithProviders(page());
    await screen.findByText('First page');
    await user.click(screen.getByRole('button', { name: /^common.next/ }));
    await screen.findByText('Last page');

    invalidate();

    await screen.findByText('Remaining meeting');
    expect(list.mock.calls).toEqual([
      [20, 0],
      [20, 20],
      [20, 20],
      [20, 0],
    ]);
    expect(screen.queryByText('meetings.list.empty_title')).not.toBeInTheDocument();
    expect(bulkDelete).not.toHaveBeenCalled();
  });
});
describe('meetings list state and account boundaries', () => {
  it('shows actions only for a selection and returns keyboard clear focus to the same select-all checkbox', async () => {
    list.mockResolvedValueOnce(response([meeting('Select and clear')]));
    const { user } = renderWithProviders(page());
    await screen.findByText('Select and clear');
    const all = screen.getByRole('checkbox', { name: 'meetings.list.select_all_page' });
    expect(
      screen.queryByRole('button', { name: 'meetings.list.clear_selection' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'meetings.list.delete_selected' })
    ).not.toBeInTheDocument();

    await user.click(rowBox('Select and clear'));
    const clearAction = screen.getByRole('button', { name: 'meetings.list.clear_selection' });
    expect(
      screen.getByRole('button', { name: 'meetings.list.delete_selected' })
    ).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'meetings.list.select_all_page' })).toBe(all);
    all.focus();
    await user.tab();
    expect(clearAction).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(screen.getByRole('checkbox', { name: 'meetings.list.select_all_page' })).toBe(all);
    expect(all).toHaveFocus();
    expect(all).not.toBeChecked();
    expect(rowBox('Select and clear')).not.toBeChecked();
    expect(
      screen.queryByRole('button', { name: 'meetings.list.clear_selection' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'meetings.list.delete_selected' })
    ).not.toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('preserves an existing disclosure, checkbox DOM, focus and selection when earlier groups arrive', async () => {
    // Local instants keep the grouping scenario valid in every test-runner zone.
    const kept = meeting('Kept timeline entry', {
      started_at: new Date(2026, 9, 15, 9).toISOString(),
      stopped_at: new Date(2026, 9, 15, 10).toISOString(),
    });
    const nextDay = meeting('Inserted day', {
      started_at: new Date(2026, 9, 16, 9).toISOString(),
      stopped_at: new Date(2026, 9, 16, 10).toISOString(),
    });
    const nextPeriod = meeting('Inserted period', {
      started_at: new Date(2026, 9, 15, 16).toISOString(),
      stopped_at: new Date(2026, 9, 15, 17).toISOString(),
    });
    list.mockResolvedValueOnce(response([kept]));
    list.mockResolvedValueOnce(response([nextDay, kept]));
    list.mockResolvedValueOnce(response([nextDay, nextPeriod, kept]));
    const { user } = renderWithProviders(page());
    await screen.findByText(kept.id);
    const checkbox = rowBox(kept.id);
    const row = checkbox.closest('li');
    const disclosure = row?.querySelector('details');
    const summary = disclosure?.querySelector('summary');
    if (!disclosure || !summary) throw new Error('Meeting details must use a native disclosure');
    await user.click(summary);
    await user.click(checkbox);
    expect(disclosure).toHaveAttribute('open');
    expect(checkbox).toHaveFocus();
    expect(checkbox).toBeChecked();

    invalidate();
    await screen.findByText(nextDay.id);
    expect(rowBox(kept.id)).toBe(checkbox);
    expect(disclosure).toBeInTheDocument();
    expect(disclosure).toHaveAttribute('open');
    expect(checkbox).toHaveFocus();
    expect(checkbox).toBeChecked();
    expect(list).toHaveBeenCalledTimes(2);

    invalidate();
    await screen.findByText(nextPeriod.id);
    expect(rowBox(kept.id)).toBe(checkbox);
    expect(disclosure).toBeInTheDocument();
    expect(disclosure).toHaveAttribute('open');
    expect(checkbox).toHaveFocus();
    expect(checkbox).toBeChecked();
    expect(list).toHaveBeenCalledTimes(3);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('keeps known rows and selection through a failed refresh and a successful retry', async () => {
    list.mockResolvedValueOnce(response([meeting('Kept meeting')]));
    const { user, rerender } = renderWithProviders(page());
    await screen.findByText('Kept meeting');
    await user.click(rowBox('Kept meeting'));

    // A new auth value for the same owner must not reset selection or reread.
    rerender(page());
    expect(rowBox('Kept meeting')).toBeChecked();
    expect(list).toHaveBeenCalledTimes(1);
    invalidate('foreign');
    expect(list).toHaveBeenCalledTimes(1);
    list.mockRejectedValueOnce(new ApiError('offline', 500));
    invalidate();

    await screen.findByText('meetings.list.load_error');
    expect(rowBox('Kept meeting')).toBeChecked();
    expect(screen.queryByText('meetings.list.empty_title')).not.toBeInTheDocument();
    list.mockResolvedValueOnce(response([meeting('Kept meeting')]));
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    await waitFor(() =>
      expect(screen.queryByText('meetings.list.load_error')).not.toBeInTheDocument()
    );
    expect(rowBox('Kept meeting')).toBeChecked();
    expect(list).toHaveBeenCalledTimes(3);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('resets paging and selection on A-to-B-to-A and rejects a late A read', async () => {
    const oldRead = Promise.withResolvers<MeetingListResponse>();
    list.mockResolvedValueOnce(response([meeting('First A')], 21));
    list.mockResolvedValueOnce(response([meeting('Selected A')], 21, 20));
    list.mockReturnValueOnce(oldRead.promise);
    list.mockResolvedValueOnce(response([meeting('Only B')]));
    list.mockResolvedValueOnce(response([meeting('Fresh A')]));
    const { user, rerender } = renderWithProviders(page());
    await screen.findByText('First A');
    await user.click(screen.getByRole('button', { name: /^common.next/ }));
    await screen.findByText('Selected A');
    await user.click(rowBox('Selected A'));
    invalidate();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3));

    rerender(page('two'));
    expect(screen.queryByText('Selected A')).not.toBeInTheDocument();
    await screen.findByText('Only B');
    await act(async () => oldRead.resolve(response([meeting('Late private A')], 21, 20)));
    expect(screen.getByText('Only B')).toBeInTheDocument();
    expect(screen.queryByText('Late private A')).not.toBeInTheDocument();

    rerender(page('one'));
    await screen.findByText('Fresh A');
    expect(rowBox('Fresh A')).not.toBeChecked();
    expect(list.mock.calls).toEqual([
      [20, 0],
      [20, 20],
      [20, 20],
      [20, 0],
      [20, 0],
    ]);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('withdraws A confirmation on account change and never revives its selection', async () => {
    list.mockResolvedValueOnce(response([meeting('Confirm A')]));
    list.mockResolvedValueOnce(response([meeting('Visible B')]));
    list.mockResolvedValueOnce(response([meeting('Confirm A')]));
    const { user, rerender } = renderWithProviders(page());
    await screen.findByText('Confirm A');
    await user.click(rowBox('Confirm A'));
    await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
    await screen.findByRole('alertdialog');

    rerender(page('two'));
    await screen.findByText('Visible B');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(bulkDelete).not.toHaveBeenCalled();
    rerender(page('one'));
    await screen.findByText('Confirm A');
    expect(rowBox('Confirm A')).not.toBeChecked();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it.each(['success', 'failure'] as const)(
    'ignores a late A deletion %s without changing B selection or feedback',
    async outcome => {
      const deleting = Promise.withResolvers<MeetingBulkDeleteResponse>();
      list.mockResolvedValueOnce(response([meeting('Delete A')]));
      list.mockResolvedValueOnce(response([meeting('Keep B')]));
      bulkDelete.mockReturnValueOnce(deleting.promise);
      const { user, rerender } = renderWithProviders(page());
      await screen.findByText('Delete A');
      await user.click(rowBox('Delete A'));
      await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
      await answerConfirmDialog(user);
      await waitFor(() => expect(bulkDelete).toHaveBeenCalledWith(['Delete A']));

      rerender(page('two'));
      await screen.findByText('Keep B');
      await user.click(rowBox('Keep B'));
      await act(async () => {
        if (outcome === 'success') deleting.resolve({ deleted: ['Delete A'], skipped: [] });
        else deleting.reject(new ApiError('private A failure', 500));
      });

      expect(rowBox('Keep B')).toBeChecked();
      expect(list).toHaveBeenCalledTimes(2);
      expect(toast.success).not.toHaveBeenCalled();
      expect(toast.info).not.toHaveBeenCalled();
      expect(toast.error).not.toHaveBeenCalled();
      expect(bulkDelete).toHaveBeenCalledTimes(1);
    }
  );
});

describe('meetings list deletion races', () => {
  it('keeps selection on a failed delete so the user can retry', async () => {
    list.mockResolvedValueOnce(response([meeting('Retry delete')]));
    bulkDelete.mockRejectedValueOnce(new ApiError('offline', 500));
    const { user } = renderWithProviders(page());
    await screen.findByText('Retry delete');
    await user.click(rowBox('Retry delete'));
    await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
    await answerConfirmDialog(user);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
    expect(rowBox('Retry delete')).toBeChecked();
    expect(screen.getByRole('button', { name: 'meetings.list.delete_selected' })).toHaveAttribute(
      'aria-disabled',
      'false'
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it('uses the partial server result once and rejects an older post-delete read after a newer invalidation', async () => {
    const deleting = Promise.withResolvers<MeetingBulkDeleteResponse>();
    const oldRead = Promise.withResolvers<MeetingListResponse>();
    list.mockResolvedValueOnce(response([meeting('Deleted'), meeting('Skipped')]));
    list.mockReturnValueOnce(oldRead.promise);
    list.mockResolvedValueOnce(response([meeting('Skipped')]));
    bulkDelete.mockReturnValueOnce(deleting.promise);
    const { user } = renderWithProviders(page());
    await screen.findByText('Deleted');
    await user.click(rowBox('Deleted'));
    await user.click(rowBox('Skipped'));
    const deleteAction = screen.getByRole('button', { name: 'meetings.list.delete_selected' });
    await user.click(deleteAction);
    await answerConfirmDialog(user);
    await waitFor(() => expect(bulkDelete).toHaveBeenCalledTimes(1));

    // Busy controls retain their name and native focusability; the handler guards writes.
    expect(deleteAction).toHaveAttribute('aria-disabled', 'true');
    expect(deleteAction).toHaveAttribute('aria-busy', 'true');
    expect(deleteAction).not.toBeDisabled();
    expect(deleteAction).toHaveAccessibleName('meetings.list.delete_selected');
    await user.click(deleteAction);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(bulkDelete).toHaveBeenCalledTimes(1);
    await act(async () =>
      deleting.resolve({
        deleted: ['Deleted'],
        skipped: [{ id: 'Skipped', code: 'meeting_in_progress' }],
      })
    );
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    invalidate();
    await waitFor(() => expect(screen.queryByText('Deleted')).not.toBeInTheDocument());
    await act(async () => oldRead.resolve(response([meeting('Deleted'), meeting('Skipped')])));

    expect(screen.getByText('Skipped')).toBeInTheDocument();
    expect(screen.queryByText('Deleted')).not.toBeInTheDocument();
    expect(rowBox('Skipped')).not.toBeChecked();
    expect(bulkDelete.mock.calls).toEqual([[['Deleted', 'Skipped']]]);
    expect(list).toHaveBeenCalledTimes(3);
    expect(toast.success).toHaveBeenCalledWith('meetings.list.bulk_deleted');
    expect(toast.info).toHaveBeenCalledWith('meetings.list.bulk_skipped');
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('meetings list retry focus', () => {
  it.each([true, false])(
    'restores focus after retry only if the retry control still owns it (%s)',
    async keepRetryFocus => {
      const retryRead = Promise.withResolvers<MeetingListResponse>();
      list.mockRejectedValueOnce(new ApiError('unavailable', 503));
      list.mockReturnValueOnce(retryRead.promise);
      const { user } = renderWithProviders(page());
      await screen.findByText('meetings.list.load_error');
      const retryAction = screen.getByRole('button', { name: 'common.retry' });
      const heading = screen.getByRole('heading', { name: 'meetings.list.title', level: 1 });
      const backToChat = screen.getByRole('button', { name: 'navigation.chat' });
      await user.click(retryAction);
      expect(retryAction).toHaveFocus();
      expect(retryAction).toHaveAttribute('aria-busy', 'true');
      await user.click(retryAction);
      expect(list).toHaveBeenCalledTimes(2);
      if (!keepRetryFocus) {
        await user.tab({ shift: true });
        expect(backToChat).toHaveFocus();
      }

      await act(async () => retryRead.resolve(response([meeting('Recovered after retry')])));
      await screen.findByText('Recovered after retry');

      await waitFor(() => expect(keepRetryFocus ? heading : backToChat).toHaveFocus());
      expect(screen.queryByText('meetings.list.load_error')).not.toBeInTheDocument();
      expect(list).toHaveBeenCalledTimes(2);
      expect(bulkDelete).not.toHaveBeenCalled();
    }
  );
});

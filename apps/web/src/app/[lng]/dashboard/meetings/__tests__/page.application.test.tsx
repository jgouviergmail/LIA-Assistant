/** The meetings list with real account lifetimes, reads and individual deletion. */
import { type ContextType } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { AuthContext, type User } from '@/lib/auth';
import { ApiError } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import type {
  MeetingBulkDeleteResponse,
  MeetingListResponse,
  MeetingSummary,
} from '@/types/meetings';

const { list, bulkDelete, toast, push } = vi.hoisted(() => ({
  list: vi.fn<typeof import('@/lib/meetings/api').meetingsApi.list>(),
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
    applyUserUpdate: () => true,
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

function deleteAction(title: string) {
  const row = screen.getByText(title).closest('li');
  if (!row) throw new Error('Meeting must belong to a list row');
  return within(row).getByRole('button', { name: 'common.delete · ' + title });
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
    expect(list.mock.calls.map(([limit, offset]) => [limit, offset])).toEqual([
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
  it('keeps the open disclosure and focused delete control when earlier groups arrive', async () => {
    const kept = meeting('Kept entry', { started_at: new Date(2026, 9, 15, 9).toISOString() });
    const newer = meeting('Newer entry', { started_at: new Date(2026, 9, 16, 9).toISOString() });
    list.mockResolvedValueOnce(response([kept]));
    list.mockResolvedValueOnce(response([newer, kept]));
    const { user } = renderWithProviders(page());
    await screen.findByText(kept.id);
    const button = deleteAction(kept.id);
    const disclosure = button.closest('li')?.querySelector('details');
    const summary = disclosure?.querySelector('summary');
    if (!summary || !disclosure) throw new Error('A row needs its native disclosure');
    await user.click(summary);
    button.focus();
    invalidate();
    await screen.findByText(newer.id);
    expect(deleteAction(kept.id)).toBe(button);
    expect(button).toHaveFocus();
    expect(disclosure).toHaveAttribute('open');
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('keeps known rows through a failed refresh and retry, ignoring a foreign invalidation', async () => {
    list.mockResolvedValueOnce(response([meeting('Kept')]));
    const { user, rerender } = renderWithProviders(page());
    await screen.findByText('Kept');
    const button = deleteAction('Kept');
    rerender(page());
    invalidate('foreign');
    expect(list).toHaveBeenCalledTimes(1);
    list.mockRejectedValueOnce(new ApiError('offline', 500));
    invalidate();
    await screen.findByText('meetings.list.load_error');
    expect(deleteAction('Kept')).toBe(button);
    list.mockResolvedValueOnce(response([meeting('Kept')]));
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    await waitFor(() =>
      expect(screen.queryByText('meetings.list.load_error')).not.toBeInTheDocument()
    );
    expect(deleteAction('Kept')).toBe(button);
    expect(list).toHaveBeenCalledTimes(3);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it('resets paging on A-to-B-to-A and rejects a late A read', async () => {
    const oldRead = Promise.withResolvers<MeetingListResponse>();
    list.mockResolvedValueOnce(response([meeting('First A')], 21));
    list.mockResolvedValueOnce(response([meeting('Last A')], 21, 20));
    list.mockReturnValueOnce(oldRead.promise);
    list.mockResolvedValueOnce(response([meeting('Only B')]));
    list.mockResolvedValueOnce(response([meeting('Fresh A')]));
    const { user, rerender } = renderWithProviders(page());
    await screen.findByText('First A');
    await user.click(screen.getByRole('button', { name: /^common.next/ }));
    await screen.findByText('Last A');
    invalidate();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3));
    rerender(page('two'));
    await screen.findByText('Only B');
    await act(async () => oldRead.resolve(response([meeting('Late private A')], 21, 20)));
    expect(screen.queryByText('Late private A')).not.toBeInTheDocument();
    rerender(page('one'));
    await screen.findByText('Fresh A');
    expect(list.mock.calls.map(([limit, offset]) => [limit, offset])).toEqual([
      [20, 0],
      [20, 20],
      [20, 20],
      [20, 0],
      [20, 0],
    ]);
    expect(bulkDelete).not.toHaveBeenCalled();
  });

  it.each(['success', 'failure'] as const)(
    'ignores a late A deletion %s after account change',
    async outcome => {
      const deleting = Promise.withResolvers<MeetingBulkDeleteResponse>();
      list.mockResolvedValueOnce(response([meeting('Delete A')]));
      list.mockResolvedValueOnce(response([meeting('Keep B')]));
      bulkDelete.mockReturnValueOnce(deleting.promise);
      const { user, rerender } = renderWithProviders(page());
      await screen.findByText('Delete A');
      await user.click(deleteAction('Delete A'));
      expect(bulkDelete).toHaveBeenCalledExactlyOnceWith(['Delete A']);
      rerender(page('two'));
      await screen.findByText('Keep B');
      deleteAction('Keep B').focus();
      await act(async () => {
        if (outcome === 'success') deleting.resolve({ deleted: ['Delete A'], skipped: [] });
        else deleting.reject(new ApiError('private A failure', 500));
      });
      expect(deleteAction('Keep B')).toHaveFocus();
      expect(list).toHaveBeenCalledTimes(2);
      expect(toast.success).not.toHaveBeenCalled();
      expect(toast.info).not.toHaveBeenCalled();
      expect(toast.error).not.toHaveBeenCalled();
    }
  );
});

describe('meetings list deletion races', () => {
  it('retains the row and its focus on a failed delete, then allows an explicit retry', async () => {
    list.mockResolvedValueOnce(response([meeting('Retry delete')]));
    bulkDelete.mockRejectedValueOnce(new ApiError('offline', 500));
    const { user } = renderWithProviders(page());
    await screen.findByText('Retry delete');
    const button = deleteAction('Retry delete');
    await user.click(button);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute('aria-disabled', 'false');
    expect(toast.success).not.toHaveBeenCalled();
    expect(list).toHaveBeenCalledTimes(1);
    list.mockResolvedValueOnce(response([]));
    bulkDelete.mockResolvedValueOnce({ deleted: ['Retry delete'], skipped: [] });
    await user.click(button);
    await waitFor(() => expect(screen.queryByText('Retry delete')).not.toBeInTheDocument());
    expect(bulkDelete).toHaveBeenCalledTimes(2);
  });

  it.each(['meeting_in_progress', 'delete_failed', 'missing-result'])(
    'does not claim deletion from %s',
    async code => {
      list.mockResolvedValue(response([meeting('Kept')]));
      bulkDelete.mockResolvedValueOnce({
        deleted: [],
        skipped: code === 'missing-result' ? [] : [{ id: 'Kept', code }],
      });
      const { user } = renderWithProviders(page());
      await screen.findByText('Kept');
      await user.click(deleteAction('Kept'));
      await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
      expect(screen.getByText('Kept')).toBeInTheDocument();
      expect(toast.success).not.toHaveBeenCalled();
      if (code === 'meeting_in_progress')
        expect(toast.info).toHaveBeenCalledWith('meetings.list.bulk_skipped');
      else expect(toast.error).toHaveBeenCalledWith('common.error');
    }
  );

  it('sends one id once and rejects an older post-delete read after newer invalidation', async () => {
    const deleting = Promise.withResolvers<MeetingBulkDeleteResponse>();
    const oldRead = Promise.withResolvers<MeetingListResponse>();
    list.mockResolvedValueOnce(response([meeting('Deleted'), meeting('Kept')]));
    list.mockReturnValueOnce(oldRead.promise);
    list.mockResolvedValueOnce(response([meeting('Kept')]));
    bulkDelete.mockReturnValueOnce(deleting.promise);
    const { user } = renderWithProviders(page());
    await screen.findByText('Deleted');
    const button = deleteAction('Deleted');
    await user.click(button);
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).not.toBeDisabled();
    expect(button).toHaveAccessibleName('common.delete · Deleted');
    await user.click(button);
    await user.click(deleteAction('Kept'));
    expect(bulkDelete).toHaveBeenCalledExactlyOnceWith(['Deleted']);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await act(async () => deleting.resolve({ deleted: ['Deleted'], skipped: [] }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    invalidate();
    await waitFor(() => expect(screen.queryByText('Deleted')).not.toBeInTheDocument());
    await act(async () => oldRead.resolve(response([meeting('Deleted'), meeting('Kept')])));
    expect(screen.queryByText('Deleted')).not.toBeInTheDocument();
    expect(screen.getByText('Kept')).toBeInTheDocument();
    expect(bulkDelete).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith('meetings.list.bulk_deleted');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it.each([true, false])(
    'restores focus after removing a row only while it owns focus (%s)',
    async keepFocus => {
      const deleting = Promise.withResolvers<MeetingBulkDeleteResponse>();
      list.mockResolvedValueOnce(response([meeting('Remove')]));
      list.mockResolvedValueOnce(response([]));
      bulkDelete.mockReturnValueOnce(deleting.promise);
      const { user } = renderWithProviders(page());
      await screen.findByText('Remove');
      await user.click(deleteAction('Remove'));
      const search = screen.getByRole('searchbox');
      if (!keepFocus) search.focus();
      await act(async () => deleting.resolve({ deleted: ['Remove'], skipped: [] }));
      await waitFor(() => expect(screen.queryByText('Remove')).not.toBeInTheDocument());
      await waitFor(() =>
        expect(
          keepFocus
            ? screen.getByRole('heading', { level: 1, name: 'meetings.list.title' })
            : search
        ).toHaveFocus()
      );
    }
  );
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
      const search = screen.getByRole('searchbox');
      await user.click(retryAction);
      expect(retryAction).toHaveFocus();
      expect(retryAction).toHaveAttribute('aria-busy', 'true');
      await user.click(retryAction);
      expect(list).toHaveBeenCalledTimes(2);
      if (!keepRetryFocus) {
        await user.tab({ shift: true });
        expect(search).toHaveFocus();
      }

      await act(async () => retryRead.resolve(response([meeting('Recovered after retry')])));
      await screen.findByText('Recovered after retry');

      await waitFor(() => expect(keepRetryFocus ? heading : search).toHaveFocus());
      expect(screen.queryByText('meetings.list.load_error')).not.toBeInTheDocument();
      expect(list).toHaveBeenCalledTimes(2);
      expect(bulkDelete).not.toHaveBeenCalled();
    }
  );
});

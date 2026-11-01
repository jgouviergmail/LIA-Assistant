/**
 * The mail screen's acts (ADR-369, Task 4.7). On the open message the reader
 * shows a read state at once and goes back to the truth whenever the provider
 * did not do it — refused, or never asked because the message's previous act
 * was still on its way (the quiet mark after a look, say). On a selection
 * every act is told as it went — all done, some done, none done — and a
 * refusal of the whole act in the refusal's own words.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';

import { act, renderHook } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { WorkbenchMailState } from '@/hooks/useWorkbenchMail';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { WorkbenchActOutcome, MailMessage, MailSummary } from '@/lib/workbench/types';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useMailActs } from '../useMailActs';

const MESSAGE: MailMessage = {
  id: 'm1',
  thread_id: 'm1',
  sender: { name: 'Ana', address: 'ana@example.org' },
  reply_to: [],
  to: [],
  cc: [],
  subject: 'Budget',
  received_at: null,
  is_read: true,
  is_starred: false,
  label_ids: [],
  body: 'Hello',
  attachments: [],
};

function listing(): WorkbenchPageState<MailSummary> {
  return {
    items: [],
    nextToken: null,
    loading: false,
    loadingMore: false,
    skipped: 0,
    truncated: false,
    error: null,
    loadMore: vi.fn(),
    refresh: vi.fn(),
    replaceItem: vi.fn(),
  };
}

function mail(setRead: WorkbenchMailState['setRead']): WorkbenchMailState {
  return {
    folders: [],
    foldersError: null,
    messages: listing(),
    pending: new Set(),
    setRead,
    trash: vi.fn(),
    applyLabels: vi.fn(),
    createLabel: vi.fn(),
    renameLabel: vi.fn(),
    deleteLabel: vi.fn(),
  };
}

/** The reader's item, kept as the hook keeps it: changes applied in order. */
function reader(message: MailMessage = MESSAGE): {
  state: WorkbenchItemState<MailMessage>;
  current: () => MailMessage;
} {
  let item = message;
  const state: WorkbenchItemState<MailMessage> = {
    item,
    loading: false,
    error: null,
    refresh: vi.fn(),
    setItem: change => {
      item = change(item);
    },
  };
  return { state, current: () => item };
}

describe('useMailActs — the open message', () => {
  it('goes back to the truth when nothing was asked of the provider', async () => {
    const nothingAsked: WorkbenchActOutcome = { done: [], failed: [] };
    const open = reader();
    const { result } = renderHook(() =>
      useMailActs('en', mail(vi.fn().mockResolvedValue(nothingAsked)), open.state)
    );

    await act(() => result.current.setOpenRead(false));

    expect(open.current().is_read).toBe(true);
  });

  it('keeps the state the provider did', async () => {
    const open = reader();
    const { result } = renderHook(() =>
      useMailActs('en', mail(vi.fn().mockResolvedValue({ done: ['m1'], failed: [] })), open.state)
    );

    await act(() => result.current.setOpenRead(false));

    expect(open.current().is_read).toBe(false);
  });
});

const REFUSED = new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } });
const ROW: MailSummary = { ...MESSAGE, snippet: '' };
const failedOne = (id: string) => ({ id, status: 'failed' as const });

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.success).mockClear();
});

describe('useMailActs — the open message, the rest of its acts', () => {
  it('rolls a refused mark back and says why, except for the quiet mark after a look', async () => {
    const open = reader({ ...MESSAGE, is_read: false });
    const setRead = vi.fn().mockRejectedValue(REFUSED);
    const { result } = renderHook(() => useMailActs('en', mail(setRead), open.state));

    await act(() => result.current.setOpenRead(true, true));
    expect(open.current().is_read).toBe(false);
    expect(toast.error).not.toHaveBeenCalled();

    await act(() => result.current.setOpenRead(true));
    expect(open.current().is_read).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable');
  });

  it('says a mark the provider did not do, and asks nothing when the state already holds', async () => {
    const open = reader();
    const setRead = vi.fn().mockResolvedValue({ done: [], failed: [failedOne('m1')] });
    const { result } = renderHook(() => useMailActs('en', mail(setRead), open.state));

    await act(() => result.current.setOpenRead(true));
    expect(setRead).not.toHaveBeenCalled();

    await act(() => result.current.setOpenRead(false));
    expect(open.current().is_read).toBe(true);
    expect(toast.error).toHaveBeenCalledWith('workbench.mail.none_done');
  });

  it('moves the open message to the trash, telling whether it went', async () => {
    const state = mail(vi.fn());
    const open = reader();
    const { result } = renderHook(() => useMailActs('en', state, open.state));

    vi.mocked(state.trash).mockResolvedValueOnce({ done: ['m1'], failed: [] });
    await expect(result.current.trashOpen()).resolves.toBe(true);
    expect(state.trash).toHaveBeenCalledWith(['m1']);
    expect(toast.success).toHaveBeenCalledWith('workbench.mail.trashed');

    vi.mocked(state.trash).mockResolvedValueOnce({ done: [], failed: [failedOne('m1')] });
    await expect(result.current.trashOpen()).resolves.toBe(false);
    expect(toast.error).toHaveBeenCalledWith('workbench.mail.none_done');

    vi.mocked(state.trash).mockRejectedValueOnce(REFUSED);
    await expect(result.current.trashOpen()).resolves.toBe(false);
    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
  });

  it('labels the open message once, and leaves it as it was when refused', async () => {
    const state = mail(vi.fn());
    const open = reader({ ...MESSAGE, label_ids: ['L1', 'L2'] });
    const { result } = renderHook(() => useMailActs('en', state, open.state));

    await act(() => result.current.labelOpen(['L2', 'L3'], ['L1']));
    expect(state.applyLabels).toHaveBeenCalledWith(
      [expect.objectContaining({ id: 'm1' })],
      ['L2', 'L3'],
      ['L1']
    );
    expect(open.current().label_ids).toEqual(['L2', 'L3']);

    vi.mocked(state.applyLabels).mockRejectedValueOnce(REFUSED);
    await act(() => result.current.labelOpen(['L9'], []));
    expect(open.current().label_ids).toEqual(['L2', 'L3']);
    expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable');
  });

  it('does nothing without an open message', async () => {
    const state = mail(vi.fn());
    const none: WorkbenchItemState<MailMessage> = { ...reader().state, item: undefined };
    const { result } = renderHook(() => useMailActs('en', state, none));

    await expect(result.current.trashOpen()).resolves.toBe(false);
    await act(() => result.current.labelOpen(['L1'], []));
    await act(() => result.current.setOpenRead(false));

    expect(state.trash).not.toHaveBeenCalled();
    expect(state.applyLabels).not.toHaveBeenCalled();
    expect(state.setRead).not.toHaveBeenCalled();
  });
});

describe('useMailActs — a selection', () => {
  it('tells some done and none done, and lets the list show a full success', async () => {
    const setRead = vi
      .fn()
      .mockResolvedValueOnce({ done: ['m1'], failed: [failedOne('m2')] })
      .mockResolvedValueOnce({ done: [], failed: [failedOne('m1')] })
      .mockResolvedValueOnce({ done: ['m1'], failed: [] });
    const { result } = renderHook(() => useMailActs('en', mail(setRead), reader().state));

    await act(() => result.current.readSelection([ROW], true));
    expect(toast.error).toHaveBeenLastCalledWith('workbench.mail.partial');
    await act(() => result.current.readSelection([ROW], false));
    expect(toast.error).toHaveBeenLastCalledWith('workbench.mail.none_done');
    await act(() => result.current.readSelection([ROW], true));

    expect(setRead).toHaveBeenLastCalledWith([ROW], true);
    expect(toast.error).toHaveBeenCalledTimes(2);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('says a refused act in the words of its refusal, or in a sentence of its own', async () => {
    const setRead = vi
      .fn()
      .mockRejectedValueOnce(REFUSED)
      .mockRejectedValueOnce(new Error('network'));
    const { result } = renderHook(() => useMailActs('en', mail(setRead), reader().state));

    await act(() => result.current.readSelection([ROW], true));
    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
    await act(() => result.current.readSelection([ROW], true));
    expect(toast.error).toHaveBeenLastCalledWith('workbench.mail.act_failed');
  });

  it('hands back exactly the messages the trash took', async () => {
    const state = mail(vi.fn());
    const { result } = renderHook(() => useMailActs('en', state, reader().state));

    vi.mocked(state.trash).mockResolvedValueOnce({ done: ['m1'], failed: [failedOne('m2')] });
    await expect(result.current.trashSelection(['m1', 'm2'])).resolves.toEqual(['m1']);
    expect(toast.error).toHaveBeenLastCalledWith('workbench.mail.partial');

    vi.mocked(state.trash).mockResolvedValueOnce({ done: ['m1', 'm2'], failed: [] });
    await expect(result.current.trashSelection(['m1', 'm2'])).resolves.toEqual(['m1', 'm2']);
    expect(toast.success).toHaveBeenCalledWith('workbench.mail.trashed');

    vi.mocked(state.trash).mockRejectedValueOnce(REFUSED);
    await expect(result.current.trashSelection(['m1'])).resolves.toEqual([]);
    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
  });

  it('is busy with its act while it runs, and free once it ends, even refused', async () => {
    let refuse: (reason: unknown) => void = () => undefined;
    const state = mail(vi.fn());
    vi.mocked(state.applyLabels).mockImplementationOnce(
      () => new Promise((_, reject) => (refuse = reject))
    );
    const { result } = renderHook(() => useMailActs('en', state, reader().state));

    let running: Promise<void> = Promise.resolve();
    act(() => {
      running = result.current.labelSelection([ROW], ['L1'], []);
    });
    expect(result.current.bulkBusy).toBe('labels');
    await act(async () => {
      refuse(REFUSED);
      await running;
    });

    expect(result.current.bulkBusy).toBeNull();
    expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable');
  });
});

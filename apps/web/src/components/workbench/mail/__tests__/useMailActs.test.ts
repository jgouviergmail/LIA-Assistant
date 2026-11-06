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

const FOLDER = 'system:inbox';
const onUnread = vi.fn();
const onSent = vi.fn();

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
  has_attachments: false,
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
    foldersTruncated: false,
    foldersError: null,
    messages: listing(),
    reread: vi.fn(),
    pending: new Set(),
    setRead,
    setStarred: vi.fn(),
    move: vi.fn(),
    deleteForever: vi.fn(),
    emptyTrash: vi.fn(),
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
      useMailActs(
        'en',
        mail(vi.fn().mockResolvedValue(nothingAsked)),
        open.state,
        FOLDER,
        onUnread,
        onSent
      )
    );

    await act(() => result.current.setOpenRead(false));

    expect(open.current().is_read).toBe(true);
  });

  it("moves the listing's figure for a message of the listing", async () => {
    const open = reader({ ...MESSAGE, is_read: false });
    const state = mail(vi.fn().mockResolvedValue({ done: ['m1'], failed: [] }));
    state.messages.items = [ROW];
    onUnread.mockClear();
    onSent.mockClear();
    const { result } = renderHook(() =>
      useMailActs('en', state, open.state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.setOpenRead(true));

    expect(onUnread).toHaveBeenCalledExactlyOnceWith(-1);
    expect(onSent).not.toHaveBeenCalled();
  });

  it('reads the figures again for a message that lives in another folder', async () => {
    const open = reader({ ...MESSAGE, is_read: false });
    onUnread.mockClear();
    onSent.mockClear();
    const { result } = renderHook(() =>
      useMailActs(
        'en',
        mail(vi.fn().mockResolvedValue({ done: ['m1'], failed: [] })),
        open.state,
        FOLDER,
        onUnread,
        onSent
      )
    );

    await act(() => result.current.setOpenRead(true));

    expect(onUnread).not.toHaveBeenCalled();
    expect(onSent).toHaveBeenCalledOnce();
  });

  it('keeps the state the provider did', async () => {
    const open = reader();
    const { result } = renderHook(() =>
      useMailActs(
        'en',
        mail(vi.fn().mockResolvedValue({ done: ['m1'], failed: [] })),
        open.state,
        FOLDER,
        onUnread,
        onSent
      )
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
    const { result } = renderHook(() =>
      useMailActs('en', mail(setRead), open.state, FOLDER, onUnread, onSent)
    );

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
    const { result } = renderHook(() =>
      useMailActs('en', mail(setRead), open.state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.setOpenRead(true));
    expect(setRead).not.toHaveBeenCalled();

    await act(() => result.current.setOpenRead(false));
    expect(open.current().is_read).toBe(true);
    expect(toast.error).toHaveBeenCalledWith('workbench.mail.none_done');
  });

  it('stars the open message at once, and goes back when refused', async () => {
    const state = mail(vi.fn());
    const open = reader();
    const { result } = renderHook(() =>
      useMailActs('en', state, open.state, FOLDER, onUnread, onSent)
    );

    vi.mocked(state.setStarred).mockResolvedValueOnce({ done: ['m1'], failed: [] });
    await act(() => result.current.setOpenStarred(true));
    expect(open.current().is_starred).toBe(true);

    vi.mocked(state.setStarred).mockRejectedValueOnce(REFUSED);
    await act(() => result.current.setOpenStarred(true));
    expect(open.current().is_starred).toBe(false);
    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
  });

  it('labels the open message once, and leaves it as it was when refused', async () => {
    const state = mail(vi.fn());
    const open = reader({ ...MESSAGE, label_ids: ['L1', 'L2'] });
    const { result } = renderHook(() =>
      useMailActs('en', state, open.state, FOLDER, onUnread, onSent)
    );

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
    const { result } = renderHook(() => useMailActs('en', state, none, FOLDER, onUnread, onSent));

    await act(() => result.current.labelOpen(['L1'], []));
    await act(() => result.current.setOpenRead(false));
    await act(() => result.current.setOpenStarred(true));

    expect(state.setStarred).not.toHaveBeenCalled();
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
    const { result } = renderHook(() =>
      useMailActs('en', mail(setRead), reader().state, FOLDER, onUnread, onSent)
    );

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
    const { result } = renderHook(() =>
      useMailActs('en', mail(setRead), reader().state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.readSelection([ROW], true));
    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
    await act(() => result.current.readSelection([ROW], true));
    expect(toast.error).toHaveBeenLastCalledWith('workbench.mail.act_failed');
  });

  it('hands back exactly the messages a move took', async () => {
    const state = mail(vi.fn());
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    vi.mocked(state.move).mockResolvedValueOnce({
      done: ['m1'],
      failed: [failedOne('m2')],
      moved: [{ id: 'm1', new_id: 'n1' }],
    });
    await expect(result.current.send(['m1', 'm2'], 'trash')).resolves.toEqual(['m1']);
    expect(state.move).toHaveBeenLastCalledWith(['m1', 'm2'], 'system:trash');
    expect(toast.error).toHaveBeenLastCalledWith('workbench.mail.partial');

    vi.mocked(state.move).mockRejectedValueOnce(REFUSED);
    await expect(result.current.send(['m1'], 'archive')).resolves.toEqual([]);
    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
  });

  it.each([
    ['archive', 'system:archive', 'workbench.mail.archived'],
    ['spam', 'system:spam', 'workbench.mail.reported_spam'],
    ['not_spam', 'system:inbox', 'workbench.mail.not_spam_done'],
    ['restore', 'system:inbox', 'workbench.mail.restored'],
  ] as const)('%s goes to %s and says so', async (kind, place, said) => {
    const state = mail(vi.fn());
    vi.mocked(state.move).mockResolvedValueOnce({
      done: ['m1'],
      failed: [],
      moved: [{ id: 'm1', new_id: 'n1' }],
    });
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.send(['m1'], kind));

    expect(state.move).toHaveBeenCalledWith(['m1'], place);
    expect(toast.success).toHaveBeenLastCalledWith(said, expect.anything());
    expect(onSent).toHaveBeenCalled();
  });

  it('sends a move to the folder it was given, and nowhere without one', async () => {
    const state = mail(vi.fn());
    vi.mocked(state.move).mockResolvedValue({ done: ['m1'], failed: [], moved: [] });
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    await expect(result.current.send(['m1'], 'move')).resolves.toEqual([]);
    expect(state.move).not.toHaveBeenCalled();

    await act(() => result.current.send(['m1'], 'move', 'Projets'));
    expect(state.move).toHaveBeenCalledWith(['m1'], 'Projets');
  });

  /** The undo of the last success toast. */
  const undoOf = () => {
    const options = vi.mocked(toast.success).mock.lastCall?.[1];
    return options?.action as { onClick: () => void } | undefined;
  };

  it('comes back from where it went, by what the act called it', async () => {
    const state = mail(vi.fn());
    vi.mocked(state.move).mockResolvedValue({
      done: ['m1'],
      failed: [],
      moved: [{ id: 'm1', new_id: 'n1' }],
    });
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.send(['m1'], 'trash'));
    await act(async () => undoOf()?.onClick());

    expect(state.move).toHaveBeenLastCalledWith(['n1'], FOLDER, 'system:trash');
    expect(state.messages.refresh).toHaveBeenCalled();
    expect(toast.success).toHaveBeenLastCalledWith('workbench.mail.undone', undefined);
  });

  it('offers no way back from a view: it says nothing of where a message was', async () => {
    const state = mail(vi.fn());
    vi.mocked(state.move).mockResolvedValue({
      done: ['m1'],
      failed: [],
      moved: [{ id: 'm1', new_id: 'n1' }],
    });
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, 'system:starred', onUnread, onSent)
    );

    await act(() => result.current.send(['m1'], 'trash'));

    expect(undoOf()).toBeUndefined();
  });

  it('offers no way back when a message cannot be named any more', async () => {
    const state = mail(vi.fn());
    vi.mocked(state.move).mockResolvedValue({
      done: ['m1', 'm2'],
      failed: [],
      moved: [
        { id: 'm1', new_id: 'n1' },
        { id: 'm2', new_id: null },
      ],
    });
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.send(['m1', 'm2'], 'archive'));

    expect(undoOf()).toBeUndefined();
  });

  it('says a way back that failed', async () => {
    const state = mail(vi.fn());
    vi.mocked(state.move).mockResolvedValueOnce({
      done: ['m1'],
      failed: [],
      moved: [{ id: 'm1', new_id: 'n1' }],
    });
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    await act(() => result.current.send(['m1'], 'archive'));
    vi.mocked(state.move).mockRejectedValueOnce(REFUSED);
    await act(async () => undoOf()?.onClick());

    expect(toast.error).toHaveBeenLastCalledWith('workbench.errors.provider_unavailable');
  });

  it('hands back what was deleted for good, and tells a trash emptied', async () => {
    const state = mail(vi.fn());
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

    vi.mocked(state.deleteForever).mockResolvedValueOnce({ done: ['m1'], failed: [] });
    await expect(result.current.deleteForever(['m1'])).resolves.toEqual(['m1']);
    expect(toast.success).toHaveBeenLastCalledWith('workbench.mail.deleted_forever', undefined);

    vi.mocked(state.emptyTrash).mockResolvedValueOnce({ deleted: 3, remaining: false });
    await act(() => result.current.emptyTrash());
    expect(toast.success).toHaveBeenLastCalledWith('workbench.mail.emptied');

    vi.mocked(state.emptyTrash).mockResolvedValueOnce({ deleted: 200, remaining: true });
    await act(() => result.current.emptyTrash());
    expect(toast.success).toHaveBeenLastCalledWith('workbench.mail.emptied_more');
  });

  it('moves the unread figure by what actually changed', async () => {
    const setRead = vi.fn().mockResolvedValue({ done: ['m1'], failed: [] });
    const state = mail(setRead);
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );
    const unreadRow = { ...state.messages.items[0]!, id: 'm1', is_read: false };
    const readRow = { ...unreadRow, id: 'm2', is_read: true };
    onUnread.mockClear();

    await act(() => result.current.readSelection([unreadRow, readRow], true));

    expect(onUnread).toHaveBeenCalledExactlyOnceWith(-1);
  });

  it('is busy with its act while it runs, and free once it ends, even refused', async () => {
    let refuse: (reason: unknown) => void = () => undefined;
    const state = mail(vi.fn());
    vi.mocked(state.applyLabels).mockImplementationOnce(
      () => new Promise((_, reject) => (refuse = reject))
    );
    const { result } = renderHook(() =>
      useMailActs('en', state, reader().state, FOLDER, onUnread, onSent)
    );

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

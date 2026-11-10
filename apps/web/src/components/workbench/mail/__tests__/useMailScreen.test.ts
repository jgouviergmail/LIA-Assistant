/**
 * The look that marks a message read (ADR-369, Task 4.7): once per opening,
 * after `MAIL_READ_DWELL_MS`, never at a glance — and never again over the
 * person's own « Mark as unread ».
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { MAIL_INBOX, MAIL_READ_DWELL_MS } from '@/lib/workbench/mail';
import type { MailMessage, MailSummary } from '@/lib/workbench/types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/mail',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import {
  useConversation,
  useFirstLook,
  useFreshListing,
  useReadAfterLook,
  type MailAddress,
} from '../useMailScreen';

describe('useConversation', () => {
  const landed = (id: string) => ({ id }) as MailMessage;
  const row = (id: string) => ({ id, thread_id: 't1' }) as MailSummary;
  const held = { items: [row('m1'), row('m2')], truncated: false };

  function reading(message: MailMessage | undefined) {
    return renderHook(
      (props: { open: boolean; message: MailMessage | undefined }) =>
        useConversation(props.open, props.message),
      { initialProps: { open: true, message } }
    );
  }

  beforeEach(() => {
    // The file's clock is frozen for the look; a read here lands on its own.
    vi.useRealTimers();
    api.get.mockReset();
    api.get.mockResolvedValue(held);
  });

  it('reads nothing before the message landed', () => {
    reading(undefined);

    expect(api.get).not.toHaveBeenCalled();
  });

  it('keeps what it read while the person walks it, and stays open', async () => {
    const { result, rerender } = reading(landed('m1'));
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    act(() => result.current.setExpanded(true));

    rerender({ open: true, message: undefined });
    rerender({ open: true, message: landed('m2') });

    expect(result.current.rows).toHaveLength(2);
    expect(result.current.expanded).toBe(true);
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('reads anew and closes for a message outside it', async () => {
    const { result, rerender } = reading(landed('m1'));
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    act(() => result.current.setExpanded(true));

    rerender({ open: true, message: landed('m9') });

    expect(result.current.expanded).toBe(false);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(api.get.mock.calls[1][1]).toMatchObject({ params: { id: 'm9' } });
  });

  it('lets go of it when the reader closes', async () => {
    const { result, rerender } = reading(landed('m1'));
    await waitFor(() => expect(result.current.rows).toHaveLength(2));

    rerender({ open: false, message: undefined });

    expect(result.current.rows).toEqual([]);
  });

  it('says a read that failed', async () => {
    api.get.mockRejectedValue(new Error('unread'));

    const { result } = reading(landed('m1'));

    await waitFor(() => expect(result.current.failed).toBe(true));
  });
});

describe('useFreshListing', () => {
  function watched(folder: string, figure: number | undefined) {
    const reread = vi.fn();
    const view = renderHook(
      (props: { folder: string; figure: number | undefined }) =>
        useFreshListing(
          props.folder,
          props.figure === undefined ? undefined : { [props.folder]: props.figure },
          reread
        ),
      { initialProps: { folder, figure } }
    );
    return { reread, ...view };
  }

  it('reads the listing again when its figure grows', () => {
    const { reread, rerender } = watched('system:inbox', 2);

    rerender({ folder: 'system:inbox', figure: 3 });

    expect(reread).toHaveBeenCalledOnce();
  });

  it('asks for nothing when the person read a message', () => {
    const { reread, rerender } = watched('system:inbox', 2);

    rerender({ folder: 'system:inbox', figure: 1 });

    expect(reread).not.toHaveBeenCalled();
  });

  it('takes another folder for what it is, never for mail arriving', () => {
    const { reread, rerender } = watched('system:inbox', 2);

    rerender({ folder: 'Projets', figure: 9 });

    expect(reread).not.toHaveBeenCalled();
  });

  it('waits for a first figure', () => {
    const { reread, rerender } = watched('system:inbox', undefined);

    rerender({ folder: 'system:inbox', figure: 4 });
    expect(reread).not.toHaveBeenCalled();

    rerender({ folder: 'system:inbox', figure: 5 });
    expect(reread).toHaveBeenCalledOnce();
  });
});

function shown(id: string, isRead: boolean): WorkbenchItemState<MailMessage> {
  return {
    item: {
      id,
      thread_id: id,
      sender: null,
      reply_to: [],
      to: [],
      cc: [],
      subject: '',
      received_at: null,
      is_read: isRead,
      is_starred: false,
      has_attachments: false,
      label_ids: [],
      body: '',
      attachments: [],
    },
    loading: false,
    error: null,
    refresh: vi.fn(),
    setItem: vi.fn(),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useFirstLook', () => {
  const summary = (id: string) => ({ id }) as MailSummary;
  const NOTHING: readonly MailSummary[] = [];
  const asked = (change: Partial<MailAddress> = {}): MailAddress => ({
    folder: MAIL_INBOX,
    openId: null,
    folderHref: () => '',
    messageHref: () => '',
    openMessage: vi.fn(),
    replaceMessage: vi.fn(),
    closeMessage: vi.fn(),
    pickFolder: vi.fn(),
    ...change,
  });
  const inbox = asked();
  const look = (
    initial: { address?: MailAddress; rows?: readonly MailSummary[]; wide?: boolean } = {}
  ) =>
    renderHook(({ address, rows, wide }) => useFirstLook(address, rows, wide), {
      initialProps: {
        address: initial.address ?? inbox,
        rows: initial.rows ?? [summary('m1'), summary('m2')],
        wide: initial.wide ?? true,
      },
    });

  it('shows the first row once the listing lands', () => {
    const { result, rerender } = look({ rows: NOTHING });
    expect(result.current.openId).toBeNull();

    rerender({ address: inbox, rows: [summary('m1'), summary('m2')], wide: true });

    expect(result.current.openId).toBe('m1');
  });

  it('keeps what it shows when a message arrives', () => {
    const { result, rerender } = look();

    rerender({ address: inbox, rows: [summary('new'), summary('m1')], wide: true });

    expect(result.current.openId).toBe('m1');
  });

  it('lets go of it for good when it is closed', () => {
    const { result, rerender } = look();

    act(() => result.current.closeMessage());
    rerender({ address: inbox, rows: [summary('new'), summary('m1')], wide: true });

    expect(result.current.openId).toBeNull();
    expect(inbox.closeMessage).not.toHaveBeenCalled();
  });

  it('gives way to what the person opens, and stays gone when that closes', () => {
    const { result, rerender } = look();

    rerender({ address: asked({ openId: 'm2' }), rows: [summary('m1')], wide: true });
    expect(result.current.openId).toBe('m2');
    rerender({ address: inbox, rows: [summary('m1')], wide: true });

    expect(result.current.openId).toBeNull();
  });

  it('stays gone once the person left the inbox and came back', () => {
    const { result, rerender } = look();

    rerender({ address: asked({ folder: 'system:sent' }), rows: [summary('s1')], wide: true });
    expect(result.current.openId).toBeNull();
    rerender({ address: inbox, rows: [summary('m1')], wide: true });

    expect(result.current.openId).toBeNull();
  });

  it('shows nothing on a visit that started on a message or in another folder', () => {
    expect(look({ address: asked({ openId: 'm2' }) }).result.current.openId).toBe('m2');
    expect(look({ address: asked({ folder: 'system:sent' }) }).result.current.openId).toBeNull();
  });

  it('shows nothing where the reader takes the list’s place, and hands the address back', () => {
    const { result, rerender } = look({ wide: false });
    expect(result.current.openId).toBeNull();

    rerender({ address: inbox, rows: [summary('m1')], wide: true });
    expect(result.current.openId).toBe('m1');
    rerender({ address: inbox, rows: [summary('m1')], wide: false });

    expect(result.current.openId).toBeNull();
  });

  it('closes what the person opened through the address itself', () => {
    const opened = asked({ openId: 'm2' });
    const { result } = look({ address: opened });

    act(() => result.current.closeMessage());

    expect(opened.closeMessage).toHaveBeenCalledTimes(1);
  });
});

describe('useReadAfterLook', () => {
  it('never marks what the person did not open, until they open it', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ asked }) => useReadAfterLook(shown('m1', false), mark, asked),
      { initialProps: { asked: false } }
    );
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS * 3));
    expect(mark).not.toHaveBeenCalled();

    rerender({ asked: true });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('marks an unread message read after a look, not at a glance', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useReadAfterLook(shown('m1', false), mark, true));

    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS - 1));
    expect(mark).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('never marks again over the person’s own « Mark as unread »', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(({ state }) => useReadAfterLook(state, mark, true), {
      initialProps: { state: shown('m1', false) },
    });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));
    rerender({ state: shown('m1', true) });

    rerender({ state: shown('m1', false) });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS * 3));

    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('looks again when the same message is opened again after a glance', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const closed: WorkbenchItemState<MailMessage> = { ...shown('m1', false), item: undefined };
    const { rerender } = renderHook(({ state }) => useReadAfterLook(state, mark, true), {
      initialProps: { state: shown('m1', false) },
    });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS / 2));
    rerender({ state: closed });

    rerender({ state: shown('m1', false) });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('looks again at another message', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(({ state }) => useReadAfterLook(state, mark, true), {
      initialProps: { state: shown('m1', false) },
    });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    rerender({ state: shown('m2', false) });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    expect(mark).toHaveBeenCalledTimes(2);
  });
});

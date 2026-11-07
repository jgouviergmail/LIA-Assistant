/**
 * The messages on screen, by what they weigh (lot 9): the mailbox's order until a line is chosen,
 * a sort that keeps it among equals, a « Priority » that never empties the screen, and rows that
 * forget the answer once they changed.
 */
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TriagedMessage } from '@/lib/workbench/assist';
import type { MailLine } from '@/lib/workbench/mail';
import type { MailSummary } from '@/lib/workbench/types';

const { post, bounds, toast } = vi.hoisted(() => ({
  post: vi.fn(),
  bounds: { value: { textMax: 100, instructionMax: 10, dictates: false } as object | null },
  toast: Object.assign(vi.fn(), { info: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values?.count ? `${key} ${String(values.count)}` : key,
  }),
}));
vi.mock('../../mail/MailSearchBar', () => ({ MAIL_CHIP: 'chip' }));

import { triagedLines, useMailTriage } from '../useMailTriage';

function line(id: string): MailLine {
  const message: MailSummary = {
    id,
    thread_id: id,
    sender: null,
    subject: id,
    snippet: '',
    received_at: null,
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
  };
  return { message, members: [message] };
}

function weighed(id: string, importance: string, category = 'other'): TriagedMessage {
  return { id, importance, category };
}

const PAGE = [line('m1'), line('m2'), line('m3')];
const ids = (lines: readonly MailLine[]) => lines.map(item => item.message.id);

function Chip({ chip }: { chip: ReactNode }) {
  return <div>{chip}</div>;
}

async function pick(chip: ReactNode, label: string) {
  const user = userEvent.setup();
  render(<Chip chip={chip} />);
  await user.click(screen.getByRole('button', { name: /workbench\.assist\.triage\.label/ }));
  await user.click(await screen.findByRole('menuitemradio', { name: label }));
}

beforeEach(() => {
  vi.clearAllMocks();
  bounds.value = { textMax: 100, instructionMax: 10, dictates: false };
});

describe('triagedLines', () => {
  const known = new Map([
    ['m1', weighed('m1', 'low', 'newsletter')],
    ['m3', weighed('m3', 'high', 'work')],
  ]);

  it('puts what matters first, what it could not read among the ordinary', () => {
    expect(ids(triagedLines(PAGE, known, 'important'))).toEqual(['m3', 'm2', 'm1']);
  });

  it('groups by kind, the unknown last', () => {
    expect(ids(triagedLines(PAGE, known, 'category'))).toEqual(['m3', 'm1', 'm2']);
  });

  it('keeps only what is priority', () => {
    expect(ids(triagedLines(PAGE, known, 'priority'))).toEqual(['m3']);
  });

  it('keeps the mailbox’s order among equals', () => {
    expect(ids(triagedLines(PAGE, new Map(), 'important'))).toEqual(['m1', 'm2', 'm3']);
  });

  it('never moves an unknown kind ahead of a known one', () => {
    const odd = new Map([['m1', weighed('m1', 'normal', 'invented')]]);
    expect(ids(triagedLines([line('m1'), line('m3')], odd, 'category'))).toEqual(['m3', 'm1']);
  });
});

describe('useMailTriage', () => {
  it('asks nothing and changes nothing until a line is chosen', () => {
    const { result } = renderHook(() => useMailTriage('en', PAGE, 25));

    expect(result.current.lines).toBe(PAGE);
    expect(result.current.on).toBe(false);
    expect(post).not.toHaveBeenCalled();
  });

  it('offers nothing where a click may not ask a model, nor on an empty page', () => {
    bounds.value = null;
    expect(renderHook(() => useMailTriage('en', PAGE, 25)).result.current.chip).toBeFalsy();

    bounds.value = { textMax: 100, instructionMax: 10, dictates: false };
    expect(renderHook(() => useMailTriage('en', [], 25)).result.current.chip).toBeFalsy();
  });

  it('weighs the page once, and sorts it', async () => {
    post.mockResolvedValue({ items: [weighed('m3', 'high')], skipped: 0, usage: null });
    const { result } = renderHook(() => useMailTriage('en', PAGE, 25));

    await pick(result.current.chip, 'workbench.assist.triage.important');

    await waitFor(() => expect(result.current.on).toBe(true));
    expect(ids(result.current.lines)).toEqual(['m3', 'm1', 'm2']);
    expect(post).toHaveBeenCalledExactlyOnceWith(
      '/tool-assists/mail/triage',
      { message_ids: ['m1', 'm2', 'm3'] },
      expect.anything()
    );
  });

  it('asks for one page at most', async () => {
    post.mockResolvedValue({ items: [weighed('m1', 'high')], skipped: 0, usage: null });
    const { result } = renderHook(() => useMailTriage('en', PAGE, 2));

    await pick(result.current.chip, 'workbench.assist.triage.important');

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0]?.[1]).toEqual({ message_ids: ['m1', 'm2'] });
  });

  it('says what could not be read', async () => {
    post.mockResolvedValue({ items: [weighed('m3', 'high')], skipped: 2, usage: null });
    const { result } = renderHook(() => useMailTriage('en', PAGE, 25));

    await pick(result.current.chip, 'workbench.assist.triage.important');

    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith('workbench.assist.triage.skipped 2')
    );
  });

  it('never empties the screen: no priority is said, and the page stays', async () => {
    post.mockResolvedValue({ items: [weighed('m1', 'normal')], skipped: 0, usage: null });
    const { result } = renderHook(() => useMailTriage('en', PAGE, 25));

    await pick(result.current.chip, 'workbench.assist.triage.priority');

    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith('workbench.assist.triage.none_priority')
    );
    expect(result.current.on).toBe(false);
    expect(result.current.lines).toBe(PAGE);
  });

  it('says a refusal and leaves the page as it stood', async () => {
    post.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useMailTriage('en', PAGE, 25));

    await pick(result.current.chip, 'workbench.assist.triage.important');

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.assist.failed'));
    expect(result.current.lines).toBe(PAGE);
  });

  it('forgets the answer once the rows changed', async () => {
    post.mockResolvedValue({ items: [weighed('m3', 'high')], skipped: 0, usage: null });
    const { result, rerender } = renderHook(
      ({ lines }: { lines: readonly MailLine[] }) => useMailTriage('en', lines, 25),
      { initialProps: { lines: PAGE as readonly MailLine[] } }
    );
    await pick(result.current.chip, 'workbench.assist.triage.important');
    await waitFor(() => expect(result.current.on).toBe(true));

    const next = [line('m4'), ...PAGE];
    act(() => rerender({ lines: next }));

    expect(result.current.on).toBe(false);
    expect(result.current.lines).toBe(next);
  });

  it('says a row’s kind only when sorted by kind', async () => {
    post.mockResolvedValue({ items: [weighed('m1', 'normal', 'work')], skipped: 0, usage: null });
    const { result } = renderHook(() => useMailTriage('en', PAGE, 25));
    expect(result.current.noteOf(PAGE[0].message)).toBeUndefined();

    await pick(result.current.chip, 'workbench.assist.triage.category');

    await waitFor(() => expect(result.current.on).toBe(true));
    expect(result.current.noteOf(PAGE[0].message)).toBe('workbench.assist.triage.categories.work');
    expect(result.current.noteOf(PAGE[1].message)).toBeUndefined();
  });
});

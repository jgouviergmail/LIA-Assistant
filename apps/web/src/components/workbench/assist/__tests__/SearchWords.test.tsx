/**
 * A search said in a sentence (lot 9): the icon shows on a sentence alone, its answer becomes
 * criteria the person sees, a refusal leaves the box as it stood.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProposedSearch } from '@/lib/workbench/assist';
import { proposedMailSearch } from '@/lib/workbench/mail';

const { post, bounds, toast } = vi.hoisted(() => ({
  post: vi.fn(),
  bounds: { value: { textMax: 100, instructionMax: 12, dictates: false } as object | null },
  toast: Object.assign(vi.fn(), { info: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import { SearchWords } from '../SearchWords';

const LABEL = 'workbench.assist.mail.search_words';
const FOUND: ProposedSearch = {
  words: 'from:Ana',
  unread: true,
  attachments: true,
  first_day: '2026-02-01',
  last_day: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  bounds.value = { textMax: 100, instructionMax: 12, dictates: false };
  post.mockResolvedValue({ search: FOUND, usage: null });
});

describe('SearchWords', () => {
  it('stays away from a plain search', () => {
    render(<SearchWords lng="en" words="invoice" onRead={vi.fn()} />);

    expect(screen.queryByRole('button', { name: LABEL })).toBeNull();
  });

  it('stays away where a click may not ask a model', () => {
    bounds.value = null;
    render(<SearchWords lng="en" words="the invoices of Ana" onRead={vi.fn()} />);

    expect(screen.queryByRole('button', { name: LABEL })).toBeNull();
  });

  it('hands the criteria over, the sentence under its bound', async () => {
    const onRead = vi.fn();
    render(<SearchWords lng="en" words="  the invoices of Ana sent last month " onRead={onRead} />);

    await userEvent.setup().click(screen.getByRole('button', { name: LABEL }));

    await waitFor(() => expect(onRead).toHaveBeenCalledWith(FOUND));
    expect(post.mock.calls[0]?.[1]).toEqual({ sentence: 'the invoices' });
  });

  it('leaves the words typed while it read: only what it cost is said', async () => {
    let answer: (value: object) => void = () => undefined;
    post.mockReturnValue(new Promise(resolve => (answer = resolve)));
    const onRead = vi.fn();
    const { rerender } = render(
      <SearchWords lng="en" words="the invoices of Ana" onRead={onRead} />
    );

    await userEvent.setup().click(screen.getByRole('button', { name: LABEL }));
    rerender(<SearchWords lng="en" words="the invoices of Ben" onRead={onRead} />);
    await act(async () =>
      answer({ search: FOUND, usage: { tokens_in: 1, tokens_out: 1, tokens_cache: 0 } })
    );

    expect(onRead).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it('says a refusal and hands nothing over', async () => {
    post.mockRejectedValue(new Error('down'));
    const onRead = vi.fn();
    render(<SearchWords lng="en" words="the invoices of Ana" onRead={onRead} />);

    await userEvent.setup().click(screen.getByRole('button', { name: LABEL }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.assist.failed'));
    expect(onRead).not.toHaveBeenCalled();
  });
});

describe('proposedMailSearch', () => {
  it('becomes the very criteria the chips show', () => {
    expect(proposedMailSearch(FOUND, true)).toEqual({
      q: 'from:Ana',
      unread: true,
      attachments: true,
      period: 'custom',
      from: '2026-02-01',
      to: '',
    });
  });

  it('leaves off what the provider cannot carry', () => {
    expect(proposedMailSearch(FOUND, false).attachments).toBe(false);
  });

  it('sets no period when no day was said', () => {
    const search = proposedMailSearch({ ...FOUND, first_day: null }, true);

    expect(search.period).toBe('any');
    expect(search.from).toBe('');
  });
});

/**
 * The drafts list (ADR-369, ADR-344): to whom each draft is addressed so far,
 * its subject and when it changed; opening one hands it to the composer, its
 * own row moves it to the trash with no dialog (nothing in the trash is lost),
 * a failed read is said beside what was read, and « More drafts » shows
 * exactly when the provider has more.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { MailDraftSummary } from '@/lib/workbench/types';

const { i18n } = vi.hoisted(() => ({
  // One stable `t` that shows its values, so « to whom » and the row's name are read.
  i18n: {
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import { DraftsView } from '../DraftsView';

function draft(id: string, overrides: Partial<MailDraftSummary> = {}): MailDraftSummary {
  return {
    id,
    to: [{ name: 'Ana', address: 'ana@example.org' }],
    subject: `Subject ${id}`,
    snippet: '',
    updated_at: '2026-10-31T09:00:00Z',
    ...overrides,
  };
}

function page(overrides: Partial<WorkbenchPageState<MailDraftSummary>> = {}) {
  return {
    items: [] as MailDraftSummary[],
    nextToken: null,
    loading: false,
    loadingMore: false,
    skipped: 0,
    truncated: false,
    error: null,
    loadMore: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn().mockResolvedValue(undefined),
    replaceItem: vi.fn(),
    ...overrides,
  };
}

function view(
  drafts: WorkbenchPageState<MailDraftSummary>,
  {
    opening = null,
    trashing = new Set<string>(),
  }: { opening?: string | null; trashing?: Set<string> } = {}
) {
  const onOpen = vi.fn();
  const onTrash = vi.fn();
  const rendered = renderWithProviders(
    <DraftsView
      lng="en"
      drafts={drafts}
      opening={opening}
      trashing={trashing}
      whenOf={item => (item.updated_at ? `when:${item.id}` : null)}
      onOpen={onOpen}
      onTrash={onTrash}
    />
  );
  return { ...rendered, onOpen, onTrash };
}

describe('DraftsView', () => {
  it('waits, then tells an empty drafts folder from one that could not be read', async () => {
    const waiting = view(page({ loading: true }));
    expect(screen.queryByRole('list')).toBeNull();
    expect(waiting.container.querySelector('[aria-busy="true"]')).not.toBeNull();
    waiting.unmount();

    const empty = view(page());
    expect(screen.getByText('workbench.mail.drafts.empty')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.states.retry' })).toBeNull();
    empty.unmount();

    const failed = page({ error: new Error('refused') });
    const { user } = view(failed);
    expect(screen.getByText('workbench.mail.drafts.failed')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.states.retry' }));
    expect(failed.refresh).toHaveBeenCalledTimes(1);
  });

  it('says to whom each draft goes so far, its subject and when it changed', () => {
    view(
      page({
        items: [
          draft('d1', {
            to: [
              { name: 'Ana', address: 'ana@example.org' },
              { name: '', address: 'bob@example.org' },
            ],
            snippet: 'See you',
          }),
          draft('d2', { to: [], subject: '', updated_at: null }),
        ],
      })
    );

    const [first, second] = within(screen.getByRole('list')).getAllByRole('listitem');
    expect(first).toHaveTextContent('workbench.mail.drafts.to(Ana, bob@example.org)');
    expect(first).toHaveTextContent('Subject d1');
    expect(first).toHaveTextContent('See you');
    expect(within(first).getByText('when:d1')).toHaveAttribute('datetime', '2026-10-31T09:00:00Z');
    expect(second).toHaveTextContent('workbench.mail.drafts.to(workbench.mail.drafts.nobody)');
    expect(second).toHaveTextContent('workbench.mail.no_subject');
    expect(second.querySelector('time')).toBeNull();
  });

  it('opens a draft into the composer, and shows the one on its way', async () => {
    const d1 = draft('d1');
    const { user, onOpen } = view(page({ items: [d1, draft('d2')] }), { opening: 'd2' });
    const [open, opening] = within(screen.getByRole('list'))
      .getAllByRole('listitem')
      .map(row => within(row).getAllByRole('button')[0]);

    await user.click(open);

    expect(onOpen).toHaveBeenCalledWith(d1);
    expect(open).not.toHaveAttribute('aria-busy');
    expect(opening).toHaveAttribute('aria-busy', 'true');
  });

  it('moves a draft to the trash from its own row, once while it is on its way', async () => {
    const d1 = draft('d1');
    const { user, onTrash, rerender } = view(page({ items: [d1] }));
    const trash = screen.getByRole('button', { name: 'workbench.mail.trash' });

    await user.click(trash);
    expect(onTrash).toHaveBeenCalledWith(d1);
    expect(screen.queryByRole('dialog')).toBeNull();
    // The row names itself for the phone's menu.
    expect(
      screen.getByRole('button', { name: 'workbench.mail.drafts.actions(Subject d1)' })
    ).toBeInTheDocument();

    rerender(
      <DraftsView
        lng="en"
        drafts={page({ items: [d1] })}
        opening={null}
        trashing={new Set(['d1'])}
        whenOf={() => null}
        onOpen={vi.fn()}
        onTrash={onTrash}
      />
    );
    await user.click(screen.getByRole('button', { name: 'workbench.mail.trash' }));
    expect(onTrash).toHaveBeenCalledTimes(1);
  });

  it('keeps what was read when a later read fails, and offers more exactly when there is more', async () => {
    const more = page({ items: [draft('d1')], nextToken: 'next', error: new Error('refused') });
    const { user, unmount } = view(more);

    expect(screen.getByRole('status')).toHaveTextContent('workbench.mail.drafts.failed');
    expect(screen.getByText('Subject d1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.mail.drafts.more' }));
    expect(more.loadMore).toHaveBeenCalledTimes(1);
    unmount();

    view(page({ items: [draft('d1')] }));
    expect(screen.queryByRole('button', { name: 'workbench.mail.drafts.more' })).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });
});

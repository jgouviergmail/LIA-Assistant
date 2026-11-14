import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationSwitcher, type ConversationSwitcherProps } from '../ConversationSwitcher';
import type { ConversationSummary } from '@/types/conversation';

function discussion(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 'annex', user_id: 'owner', kind: 'secondary', revision: 7, title: 'Travel',
    message_count: 3, total_tokens: 0, created_at: '', updated_at: '', ...overrides,
  };
}

function props(overrides: Partial<ConversationSwitcherProps> = {}): ConversationSwitcherProps {
  return {
    current: null,
    page: { items: [discussion()], total_count: 2, offset: 1, limit: 1 },
    loading: false,
    error: false,
    rules: { creation_enabled: true, title_max_length: 500, title_pattern: '^[^\\x00]*$',
      background_runs_enabled: true, offset_max: 1000, page_default_limit: 1, page_max_limit: 10 },
    onOpen: vi.fn(), onSelect: vi.fn(), onCreate: vi.fn(async () => {}),
    onRename: vi.fn(async () => {}), onDelete: vi.fn(async () => {}), onPage: vi.fn(), ...overrides,
  };
}

function openSwitcher() {
  fireEvent.click(screen.getByRole('button', { name: 'chat.discussions.open' }));
  return screen.getByRole('dialog', { name: 'chat.discussions.heading' });
}

describe('discussion catalogue', () => {
  it('keeps Main first on every page and selects the chosen row without deleting it', () => {
    const options = props();
    render(<ConversationSwitcher {...options} />);
    const dialog = openSwitcher();
    const rows = within(dialog).getAllByRole('listitem');
    const main = within(rows[0]).getByRole('button', { name: 'chat.discussions.main' });
    expect(main).toHaveAttribute('aria-current', 'true');
    // Main is neither renamed nor deleted: its row offers no such act.
    expect(within(rows[0]).queryByRole('button', { name: /rename_action|delete_action/ })).toBeNull();
    fireEvent.click(within(rows[1]).getByRole('button', { name: 'Travel' }));
    expect(options.onSelect).toHaveBeenCalledWith(discussion());
    expect(options.onDelete).not.toHaveBeenCalled();
  });

  it('keeps the reviewed identity and attempt after a lost deletion response', async () => {
    const onDelete = vi.fn<ConversationSwitcherProps['onDelete']>()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(undefined);
    const options = props({ onDelete });
    const { rerender } = render(<ConversationSwitcher {...options} />);
    openSwitcher();
    // RowActions renders a labelled desktop button and a compact mobile menu.
    fireEvent.click(screen.getByRole('button', { name: 'chat.discussions.delete_action' }));
    rerender(<ConversationSwitcher {...options} current={discussion({ id: 'other', revision: 2 })} />);
    const confirm = within(screen.getByRole('alertdialog')).getByRole('button', { name: 'chat.discussions.delete' });
    fireEvent.click(confirm);
    await screen.findByText('chat.discussions.operation_error');
    expect(onDelete.mock.calls[0]?.[0]).toEqual(discussion());
    fireEvent.click(confirm);
    await screen.findByRole('dialog', { name: 'chat.discussions.heading' });
    expect(onDelete.mock.calls[1]).toEqual(onDelete.mock.calls[0]);
  });

  it('keeps the pressed paging control in the tab order while its page loads, ignoring a second press', () => {
    const options = props({ page: { items: [discussion()], total_count: 3, offset: 1, limit: 1 } });
    const { rerender } = render(<ConversationSwitcher {...options} />);
    const dialog = openSwitcher();
    const next = within(dialog).getByRole('button', { name: 'chat.discussions.next' });
    next.focus();
    fireEvent.click(next);
    expect(options.onPage).toHaveBeenCalledExactlyOnceWith(2);

    rerender(<ConversationSwitcher {...options} loading />);
    // A natively disabled button is blurred and leaves the tab order: the
    // keyboard user would land back on the page body.
    expect(next).not.toBeDisabled();
    expect(next).toHaveAttribute('aria-disabled', 'true');
    expect(next).toHaveFocus();
    fireEvent.click(next);
    fireEvent.click(within(dialog).getByRole('button', { name: 'chat.discussions.previous' }));
    expect(options.onPage).toHaveBeenCalledTimes(1);

    rerender(<ConversationSwitcher {...options} />);
    expect(next).not.toHaveAttribute('aria-disabled');
    fireEvent.click(next);
    expect(options.onPage).toHaveBeenCalledTimes(2);
  });
});

describe('exporting a discussion', () => {
  it('offers each listed discussion as a download of that exact generation', () => {
    render(<ConversationSwitcher {...props()} />);
    const rows = within(openSwitcher()).getAllByRole('listitem');

    // RowActions draws the act twice (an icon from `sm` up, a menu entry below).
    const [annex] = within(rows[1]).getAllByRole('link', {
      name: 'chat.discussions.export_action',
    });
    expect(annex).toHaveAttribute('download');
    const address = new URL(annex.getAttribute('href') ?? '', 'https://lia.example');
    expect(address.pathname.endsWith('/conversations/me/export')).toBe(true);
    expect(address.searchParams.get('conversation_id')).toBe('annex');
    expect(address.searchParams.get('conversation_revision')).toBe('7');
  });

  it('offers Main without a selection, on a page that does not list it', () => {
    // The page holds the annex alone (offset 1), and the account has a Main.
    render(<ConversationSwitcher {...props()} />);
    const rows = within(openSwitcher()).getAllByRole('listitem');

    const [main] = within(rows[0]).getAllByRole('link', {
      name: 'chat.discussions.export_action',
    });
    expect(new URL(main.getAttribute('href') ?? '', 'https://lia.example').search).toBe('');
  });

  it('offers nothing to export to an account that has no discussion yet', () => {
    render(
      <ConversationSwitcher
        {...props({ page: { items: [], total_count: 0, offset: 0, limit: 1 } })}
      />
    );
    const rows = within(openSwitcher()).getAllByRole('listitem');

    expect(within(rows[0]).queryByRole('link')).toBeNull();
  });

  it('stays available while switching is blocked: a download leaves nothing behind', () => {
    render(<ConversationSwitcher {...props({ blockedReason: 'chat.discussions.inline_busy' })} />);
    const rows = within(openSwitcher()).getAllByRole('listitem');

    expect(
      within(rows[1]).getAllByRole('link', { name: 'chat.discussions.export_action' })[0]
    ).toHaveAttribute('href');
  });
});

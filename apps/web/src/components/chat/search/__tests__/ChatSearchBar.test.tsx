/**
 * ChatSearchBar — render/interaction tests (QW-2).
 *
 * Oracles by role/accessible name: status line, server results with marked
 * excerpts and jump buttons, history-view banner with "back to present",
 * mobile input row with Escape-to-close, and (lot 12) the discussion a result
 * was found in, named when it is not the one on screen.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ChatSearchBar, type ChatSearchBarProps } from '../ChatSearchBar';
import type { DiscussionSearchResult } from '@/hooks/useConversation';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

const HERE = 'main-1';

function row(overrides: Partial<DiscussionSearchResult>): DiscussionSearchResult {
  return {
    message_id: 'r1',
    role: 'assistant',
    content: 'On confirme la réunion de mardi matin',
    created_at: '2026-06-01T10:00:00.000Z',
    conversation_id: HERE,
    conversation_kind: 'main',
    conversation_title: null,
    conversation_revision: 0,
    ...overrides,
  };
}

function makeProps(overrides: Partial<ChatSearchBarProps> = {}): ChatSearchBarProps {
  return {
    searchQuery: '',
    setSearchQuery: vi.fn(),
    loadedMatchCount: 0,
    serverSearchAvailable: false,
    panelOpen: false,
    serverResults: [],
    serverHasMore: false,
    serverLoading: false,
    serverError: false,
    excerptTerm: '',
    historyView: false,
    jumpDisabled: false,
    currentDiscussionId: HERE,
    canOpenOtherDiscussions: true,
    mobileOpen: false,
    onCloseMobile: vi.fn(),
    onRunServerSearch: vi.fn(),
    onLoadMoreServerResults: vi.fn(),
    onClosePanel: vi.fn(),
    onJump: vi.fn(),
    onReturnToPresent: vi.fn(),
    ...overrides,
  };
}

describe('ChatSearchBar', () => {
  it('renders nothing when idle', () => {
    const { container } = render(<ChatSearchBar {...makeProps()} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the loaded-match counter and the search-all affordance', () => {
    const props = makeProps({
      searchQuery: 'reunion',
      loadedMatchCount: 3,
      serverSearchAvailable: true,
    });
    render(<ChatSearchBar {...props} />);

    expect(screen.getByRole('status').textContent).toContain('count=3');
    fireEvent.click(screen.getByRole('button', { name: 'chat.search.search_all' }));
    expect(props.onRunServerSearch).toHaveBeenCalled();
  });

  it('renders dated results with a marked excerpt and jumps on click', () => {
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [row({})],
    });
    render(<ChatSearchBar {...props} />);

    const jump = screen.getByRole('button', { name: /chat\.search\.jump_aria/ });
    expect(jump.querySelector('mark.lia-search-mark')?.textContent).toBe('réunion');
    fireEvent.click(jump);
    expect(props.onJump).toHaveBeenCalledWith(expect.objectContaining({ message_id: 'r1' }));
    // A result of the discussion on screen names no discussion.
    expect(screen.queryByText(/chat\.search\.in_discussion/)).toBeNull();
  });

  it('holds jumps within this discussion while a stream is active, keeping them focusable', () => {
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [row({})],
      jumpDisabled: true,
    });
    render(<ChatSearchBar {...props} />);

    const jump = screen.getByRole('button', { name: /chat\.search\.jump_aria/ });
    // `aria-disabled`, never `disabled`: a stream starting under a focused
    // result must not blur it (apps/web/CLAUDE.md, refresh/busy rule).
    expect(jump).toHaveAttribute('aria-disabled', 'true');
    expect(jump).not.toBeDisabled();
    fireEvent.click(jump);
    expect(props.onJump).not.toHaveBeenCalled();
  });

  it('keeps a result found elsewhere open while a stream runs here, when this discussion may be left', () => {
    const elsewhere = row({ conversation_id: 'annex-1', conversation_kind: 'secondary', conversation_title: 'T' });
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [elsewhere],
      jumpDisabled: true,
      canOpenOtherDiscussions: true,
    });
    render(<ChatSearchBar {...props} />);

    const jump = screen.getByRole('button', { name: /chat\.search\.jump_other_aria/ });
    expect(jump).not.toHaveAttribute('aria-disabled');
    fireEvent.click(jump);
    expect(props.onJump).toHaveBeenCalledWith(elsewhere);
  });

  it('names the discussion of a result found elsewhere, and opens it on click', () => {
    const elsewhere = row({
      message_id: 'r2',
      conversation_id: 'annex-1',
      conversation_kind: 'secondary',
      conversation_title: 'Travaux',
    });
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [elsewhere, row({ message_id: 'r3', conversation_id: 'main-0' })],
      currentDiscussionId: 'annex-0',
    });
    render(<ChatSearchBar {...props} />);

    const annex = screen.getByRole('button', { name: /chat\.search\.jump_other_aria\|name=Travaux/ });
    expect(annex.textContent).toContain('chat.search.in_discussion|name=Travaux');
    // Main's name is the reader's translation, never a stored title.
    expect(
      screen.getByRole('button', { name: /chat\.search\.jump_other_aria\|name=chat\.discussions\.main/ })
    ).toBeTruthy();
    fireEvent.click(annex);
    expect(props.onJump).toHaveBeenCalledWith(elsewhere);
  });

  it('holds results found elsewhere while this discussion cannot be left', () => {
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [row({ conversation_id: 'annex-1', conversation_kind: 'secondary', conversation_title: 'T' })],
      canOpenOtherDiscussions: false,
    });
    render(<ChatSearchBar {...props} />);

    const jump = screen.getByRole('button', { name: /chat\.search\.jump_other_aria/ });
    expect(jump).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(jump);
    expect(props.onJump).not.toHaveBeenCalled();
  });

  it('counts the results as all there are only once no more follow (ADR-185)', () => {
    const complete = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [row({})],
    });
    const { unmount } = render(<ChatSearchBar {...complete} />);
    expect(screen.getByText('chat.search.remote_count|count=1')).toBeInTheDocument();
    unmount();

    // More follow: the count is the most recent ones', never « N results ».
    render(<ChatSearchBar {...complete} serverHasMore />);
    expect(screen.getByText('chat.search.remote_count_partial|count=1')).toBeInTheDocument();
    expect(screen.queryByText('chat.search.remote_count|count=1')).toBeNull();
  });

  it('offers load-more when the server has more results', () => {
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [row({})],
      serverHasMore: true,
    });
    render(<ChatSearchBar {...props} />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.search.load_more' }));
    expect(props.onLoadMoreServerResults).toHaveBeenCalled();
  });

  it('shows the history banner and returns to present', () => {
    const props = makeProps({ historyView: true });
    render(<ChatSearchBar {...props} />);

    expect(screen.getByText('chat.search.history_view')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'chat.search.back_to_present' }));
    expect(props.onReturnToPresent).toHaveBeenCalled();
  });

  it('renders the mobile input row and closes on Escape', () => {
    const props = makeProps({ mobileOpen: true });
    render(<ChatSearchBar {...props} />);

    const input = screen.getByRole('searchbox', { name: 'conversations.search_placeholder' });
    fireEvent.change(input, { target: { value: 'piz' } });
    expect(props.setSearchQuery).toHaveBeenCalledWith('piz');

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(props.onCloseMobile).toHaveBeenCalled();
  });
});

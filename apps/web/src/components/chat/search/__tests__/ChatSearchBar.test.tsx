/**
 * ChatSearchBar — render/interaction tests (QW-2).
 *
 * Oracles by role/accessible name: status line, server results with marked
 * excerpts and jump buttons, history-view banner with "back to present",
 * mobile input row with Escape-to-close.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ChatSearchBar, type ChatSearchBarProps } from '../ChatSearchBar';
import type { ConversationMessage } from '@/hooks/useConversation';

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

function row(overrides: Partial<ConversationMessage>): ConversationMessage {
  return {
    id: 'r1',
    role: 'assistant',
    content: 'On confirme la réunion de mardi matin',
    message_metadata: null,
    created_at: '2026-06-01T10:00:00.000Z',
    tokens_in: null,
    tokens_out: null,
    tokens_cache: null,
    cost_eur: null,
    google_api_requests: null,
    stt_provider: null,
    stt_audio_duration_seconds: null,
    stt_cost_eur: null,
    tts_provider: null,
    tts_model: null,
    tts_characters: null,
    tts_cost_eur: null,
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
    expect(props.onJump).toHaveBeenCalledWith(expect.objectContaining({ id: 'r1' }));
  });

  it('disables jumps while a stream is active', () => {
    const props = makeProps({
      searchQuery: 'reunion',
      panelOpen: true,
      excerptTerm: 'reunion',
      serverResults: [row({})],
      jumpDisabled: true,
    });
    render(<ChatSearchBar {...props} />);

    const jump = screen.getByRole('button', { name: /chat\.search\.jump_aria/ });
    expect(jump).toHaveProperty('disabled', true);
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

/**
 * Where the bubble draws its bookmark toggle (ADR-282).
 *
 * The gate is the bubble's own: every archived assistant answer with text —
 * a proactive notification included, it is an answer a person may want to
 * keep — and never an active stream (its id is not known yet), a bubble with
 * nothing to keep, or a chat whose instance does not offer bookmarks.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeMessage, makeUser } from '@/__tests__/factories';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { BookmarkStateProvider } from '@/lib/bookmark-state-context';
import { usePsycheStore } from '@/stores/psycheStore';
import type { Message } from '@/types/chat';

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn(), loading: false, error: null }),
}));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: api, ApiError: class extends Error {} }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ChatMessage, type ChatMessageProps } from '../ChatMessage';

function renderInChat(message: Message, props: Partial<ChatMessageProps> = {}, enabled = true) {
  return renderWithProviders(
    <BookmarkStateProvider enabled={enabled}>
      <ChatMessage message={message} isUser={false} {...props} />
    </BookmarkStateProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ message_ids: {} });
  usePsycheStore.getState().reset();
  useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: false }) });
});

describe('the bookmark toggle on a bubble', () => {
  it('sits in the action row of an archived answer, beside copy', () => {
    renderInChat(makeMessage({ metadata: { message_db_id: 'db-1' } }));

    const toggle = screen.getByTestId('bookmark-toggle');
    const copy = screen.getByRole('button', { name: 'chat.message.copy' });
    expect(toggle.parentElement).toBe(copy.parentElement);
    expect(copy.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('is offered on a proactive notification too — it is an answer worth keeping', () => {
    renderInChat(
      makeMessage({
        metadata: {
          type: 'proactive_interest',
          target_id: '33333333-3333-4333-8333-333333333333',
          feedback_enabled: true,
          message_db_id: 'db-9',
        },
      })
    );

    expect(screen.getByTestId('bookmark-toggle')).toBeInTheDocument();
  });

  it('is absent while the answer is still streaming', () => {
    renderInChat(makeMessage({ metadata: { message_db_id: 'db-1' } }), {
      isActiveStream: true,
      streamPhase: 'answer',
    });

    expect(screen.queryByTestId('bookmark-toggle')).not.toBeInTheDocument();
  });

  it('is absent without an archived id, and on a bubble with nothing to keep', () => {
    const { unmount } = renderInChat(makeMessage());
    expect(screen.queryByTestId('bookmark-toggle')).not.toBeInTheDocument();
    unmount();

    renderInChat(makeMessage({ content: '   ', metadata: { message_db_id: 'db-1' } }));
    expect(screen.queryByTestId('bookmark-toggle')).not.toBeInTheDocument();
  });

  it('is absent when the instance does not offer bookmarks', () => {
    renderInChat(makeMessage({ metadata: { message_db_id: 'db-1' } }), {}, false);

    expect(screen.queryByTestId('bookmark-toggle')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});

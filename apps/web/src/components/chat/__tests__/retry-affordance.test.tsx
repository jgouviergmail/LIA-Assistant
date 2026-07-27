/**
 * Retry affordance (W3) — where the button appears, and what it replays.
 *
 * A failed turn used to be a dead end: an anonymous assistant bubble carrying
 * the error text, leaving the user to find their question and retype it. The
 * reducer now pins the prompt on the bubble; these tests pin WHERE the button
 * may appear (the latest retryable error, never an older one) and that it hands
 * back the exact prompt.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { Message } from '@/types/chat';

// Same harness as ChatMessage.test.tsx: the bubble reads the session for the
// token-display preference, which is irrelevant here.
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));

const { ChatMessage, retryPromptOf } = await import('@/components/chat/ChatMessage');
const { lastRetryableErrorId } = await import('@/components/chat/ChatMessageList');

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'Contenu',
    timestamp: new Date('2026-07-26T10:00:00Z'),
    ...overrides,
  };
}

const errorBubble = (id: string, retryPrompt?: string): Message =>
  message({
    id,
    content: 'Connexion perdue.',
    metadata: { type: 'error', ...(retryPrompt ? { retryPrompt } : {}) },
  });

describe('retryPromptOf — what a bubble offers to replay', () => {
  it('returns the pinned prompt of an error bubble', () => {
    expect(retryPromptOf(errorBubble('e1', 'Ma question'))).toBe('Ma question');
  });

  it('returns nothing for an ordinary answer, even one that looks like an error', () => {
    expect(retryPromptOf(message({ content: 'Une erreur est survenue' }))).toBeUndefined();
  });

  it('returns nothing when the error pinned no prompt', () => {
    expect(retryPromptOf(errorBubble('e1'))).toBeUndefined();
  });

  it('rejects a non-string prompt', () => {
    // The metadata bag is `Record<string, unknown>`: a malformed payload must
    // not reach the click handler as a non-string.
    const malformed = message({ metadata: { type: 'error', retryPrompt: 42 } });
    expect(retryPromptOf(malformed)).toBeUndefined();
  });

  it('rejects an empty prompt', () => {
    expect(
      retryPromptOf(message({ metadata: { type: 'error', retryPrompt: '' } }))
    ).toBeUndefined();
  });

  it('returns nothing for a bubble with no metadata at all', () => {
    expect(retryPromptOf(message())).toBeUndefined();
  });
});

describe('lastRetryableErrorId — which bubble may offer a retry', () => {
  it('finds nothing in a conversation without errors', () => {
    expect(lastRetryableErrorId([message({ id: 'a' }), message({ id: 'b' })])).toBeNull();
  });

  it('selects the error bubble when it pinned a prompt', () => {
    expect(lastRetryableErrorId([message({ id: 'a' }), errorBubble('e1', 'Ma question')])).toBe(
      'e1'
    );
  });

  it('selects nothing when the latest error pinned no prompt', () => {
    // A proactive turn can fail with no question behind it — there is nothing
    // to replay, so no button.
    expect(lastRetryableErrorId([errorBubble('e1')])).toBeNull();
  });

  it('never offers a retry on an OLDER error', () => {
    // Replaying a stale failure would drop a question into a conversation that
    // has since moved on.
    const messages = [
      errorBubble('e1', 'Ancienne question'),
      message({ id: 'a', role: 'user', content: 'Nouvelle question' }),
      message({ id: 'b', content: 'Réponse' }),
    ];
    expect(lastRetryableErrorId(messages)).toBeNull();
  });

  it('takes the most recent error when several failed', () => {
    const messages = [errorBubble('e1', 'Première'), errorBubble('e2', 'Seconde')];
    expect(lastRetryableErrorId(messages)).toBe('e2');
  });

  it('stops at the latest error even if an older one is retryable', () => {
    // The newest error has no prompt: no retry, and we must NOT fall back to
    // the older retryable one.
    const messages = [errorBubble('e1', 'Première'), errorBubble('e2')];
    expect(lastRetryableErrorId(messages)).toBeNull();
  });
});

describe('ChatMessage — the retry button', () => {
  it('offers a retry on an error bubble that carries a prompt', () => {
    renderWithProviders(
      <ChatMessage message={errorBubble('e1', 'Ma question')} isUser={false} onRetry={vi.fn()} />
    );
    expect(screen.getByRole('button', { name: 'chat.message.retry' })).toBeInTheDocument();
  });

  it('offers none without an onRetry handler (older error, or list opted out)', () => {
    renderWithProviders(<ChatMessage message={errorBubble('e1', 'Ma question')} isUser={false} />);
    expect(screen.queryByRole('button', { name: 'chat.message.retry' })).toBeNull();
  });

  it('offers none on an ordinary answer', () => {
    renderWithProviders(<ChatMessage message={message()} isUser={false} onRetry={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'chat.message.retry' })).toBeNull();
  });

  it('offers none when the error pinned no prompt', () => {
    renderWithProviders(
      <ChatMessage message={errorBubble('e1')} isUser={false} onRetry={vi.fn()} />
    );
    expect(screen.queryByRole('button', { name: 'chat.message.retry' })).toBeNull();
  });

  it('hands back the exact pinned prompt', async () => {
    const onRetry = vi.fn();
    const { user } = renderWithProviders(
      <ChatMessage
        message={errorBubble('e1', 'Quelle météo demain ?')}
        isUser={false}
        onRetry={onRetry}
      />
    );

    await user.click(screen.getByRole('button', { name: 'chat.message.retry' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledWith('Quelle météo demain ?');
  });

  it('keeps the copy action alongside it', () => {
    // The retry is additive: an error bubble is still copyable (users paste
    // error text into support requests).
    renderWithProviders(
      <ChatMessage message={errorBubble('e1', 'Ma question')} isUser={false} onRetry={vi.fn()} />
    );
    expect(screen.getByRole('button', { name: 'chat.message.copy' })).toBeInTheDocument();
  });
});

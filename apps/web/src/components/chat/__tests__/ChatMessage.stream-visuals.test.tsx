/**
 * ChatMessage — progress→answer cross-fade (W5) wiring.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import { ChatMessage, type ChatMessageProps, isFreshProactive } from '../ChatMessage';
import { TooltipProvider } from '@/components/ui/tooltip';
import { usePsycheStore } from '@/stores/psycheStore';
import type { Message } from '@/types/chat';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn() }),
}));

const MSG = {
  id: 'a-1',
  role: 'assistant',
  content: 'Hello world',
  timestamp: new Date(),
} as Message;

function renderMessage(props: Partial<ChatMessageProps> = {}) {
  return render(
    <TooltipProvider>
      <ChatMessage message={MSG} isUser={false} {...props} />
    </TooltipProvider>
  );
}

describe('isFreshProactive (F4 arrival guard)', () => {
  const NOW = 1_000_000;

  it('is fresh within the 10 s window (live push)', () => {
    expect(isFreshProactive(NOW - 2_000, NOW)).toBe(true);
    expect(isFreshProactive(NOW, NOW)).toBe(true);
  });

  it('tolerates small clock skew (slightly future timestamp)', () => {
    expect(isFreshProactive(NOW + 3_000, NOW)).toBe(true);
  });

  it('is stale beyond the window (history-loaded row)', () => {
    expect(isFreshProactive(NOW - 60_000, NOW)).toBe(false);
    expect(isFreshProactive(NOW - 11_000, NOW)).toBe(false);
  });
});

describe('ChatMessage — phase cross-fade (W5)', () => {
  beforeEach(() => {
    usePsycheStore.getState().reset();
  });

  it('plays the fade on the answer phase of the active message', () => {
    const { container } = renderMessage({ isActiveStream: true, streamPhase: 'answer' });
    expect(container.querySelector('.animate-phase-fade')).not.toBeNull();
  });

  it('does not fade during the progress phase nor on settled messages', () => {
    const progress = renderMessage({ isActiveStream: true, streamPhase: 'progress' });
    expect(progress.container.querySelector('.animate-phase-fade')).toBeNull();

    const settled = renderMessage();
    expect(settled.container.querySelector('.animate-phase-fade')).toBeNull();
  });
});

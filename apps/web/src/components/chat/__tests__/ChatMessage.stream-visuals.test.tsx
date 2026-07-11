/**
 * ChatMessage — mood glow (W2) and progress→answer cross-fade (W5) wiring.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import { ChatMessage, type ChatMessageProps } from '../ChatMessage';
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

function bubble(container: HTMLElement): HTMLElement {
  return container.querySelector('.message-bubble-assistant') as HTMLElement;
}

function renderMessage(props: Partial<ChatMessageProps> = {}) {
  return render(
    <TooltipProvider>
      <ChatMessage message={MSG} isUser={false} {...props} />
    </TooltipProvider>
  );
}

describe('ChatMessage — mood glow (W2)', () => {
  beforeEach(() => {
    usePsycheStore.getState().reset();
  });

  it('applies the mood color glow on the actively streaming bubble', () => {
    usePsycheStore.setState({ enabled: true, displayAvatar: true, moodLabel: 'playful' });
    const { container } = renderMessage({ isActiveStream: true, streamPhase: 'answer' });
    const el = bubble(container);
    expect(el.className).toContain('mood-glow');
    expect(el.style.getPropertyValue('--mood-color')).toBe('#f472b6');
  });

  it('keeps the regular border when the message is not streaming', () => {
    usePsycheStore.setState({ enabled: true, displayAvatar: true, moodLabel: 'playful' });
    const { container } = renderMessage();
    expect(bubble(container).className).not.toContain('mood-glow');
  });

  it('keeps the regular border when psyche visuals are hidden', () => {
    usePsycheStore.setState({ enabled: false, displayAvatar: true, moodLabel: 'playful' });
    const { container } = renderMessage({ isActiveStream: true, streamPhase: 'answer' });
    expect(bubble(container).className).not.toContain('mood-glow');
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

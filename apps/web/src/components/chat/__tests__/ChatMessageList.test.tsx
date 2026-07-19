/**
 * ChatMessageList — the conversation surface (the pure helpers are covered in
 * `ChatMessageList.logic.test.tsx`).
 *
 * What is pinned here is what the user actually experiences:
 *  - the **defensive branch**: a malformed `messages` prop shows an error card
 *    instead of crashing the whole chat, and logs it *without* the content
 *    (PII protection);
 *  - the empty state greets according to the local hour, deep night included;
 *  - **infinite scroll upward**: the sentinel only exists while older history
 *    remains, and it must not call back while a fetch is already in flight —
 *    otherwise scrolling near the top fires a burst of duplicate requests;
 *  - only the *last* assistant row animates its emoji, and only the streaming
 *    row is flagged as active.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { makeMessage } from '@/__tests__/factories';
import type { Message } from '@/types/chat';

const { logger } = vi.hoisted(() => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
vi.mock('@/lib/logger', () => ({ logger }));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: vi.fn() }) }));

import { ChatMessageList, type ChatMessageListProps } from '../ChatMessageList';

/** A controllable IntersectionObserver — jsdom ships none. */
class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];

  observed: Element[] = [];
  disconnected = false;

  constructor(
    readonly callback: (entries: { isIntersecting: boolean }[]) => void,
    readonly options?: { root?: Element | null; rootMargin?: string }
  ) {
    FakeIntersectionObserver.instances.push(this);
  }

  observe(element: Element) {
    this.observed.push(element);
  }

  disconnect() {
    this.disconnected = true;
  }

  /** Simulates the sentinel entering (or leaving) the viewport. */
  trigger(isIntersecting = true) {
    this.callback([{ isIntersecting }]);
  }
}

const lastObserver = () =>
  FakeIntersectionObserver.instances[FakeIntersectionObserver.instances.length - 1];

function render(props: Partial<ChatMessageListProps> = {}) {
  return renderWithProviders(<ChatMessageList messages={[]} {...props} />);
}

const user = (id: string, content = 'Bonjour') =>
  makeMessage({ id, role: 'user', content }) as Message;
const assistant = (id: string, content = 'Bonjour à vous') =>
  makeMessage({ id, role: 'assistant', content }) as Message;

beforeEach(() => {
  vi.clearAllMocks();
  FakeIntersectionObserver.instances = [];
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('ChatMessageList — malformed input', () => {
  it('shows an error card instead of crashing the conversation', () => {
    // The prop is typed, but the value crosses an API/state boundary at runtime.
    render({ messages: null as unknown as Message[] });

    expect(screen.getByText('chat.error.title')).toBeInTheDocument();
    expect(screen.getByText('chat.error.message')).toBeInTheDocument();
  });

  it('logs the type without ever logging the content', () => {
    render({ messages: 'oops' as unknown as Message[] });

    expect(logger.error).toHaveBeenCalledWith(
      'messages_invalid_type',
      undefined,
      expect.objectContaining({ component: 'ChatMessageList', receivedType: 'string' })
    );
    const [, , context] = logger.error.mock.calls[0];
    expect(JSON.stringify(context)).not.toContain('oops');
  });
});

describe('ChatMessageList — empty conversation', () => {
  /** Freezes the clock at a given local hour before mounting. */
  function atHour(hour: number) {
    vi.useFakeTimers();
    const now = new Date(2026, 6, 19, hour, 30, 0);
    vi.setSystemTime(now);
  }

  it('greets and explains what the assistant is for', () => {
    atHour(14);
    render({ messages: [] });

    expect(screen.getByText('chat.empty_state.title')).toBeInTheDocument();
    expect(screen.getByText('chat.empty_state.description')).toBeInTheDocument();
  });

  it('adds the nightly consolidation note deep at night', () => {
    atHour(2);
    render({ messages: [] });

    expect(screen.getByText('chat.empty_state.night_note')).toBeInTheDocument();
  });

  it('stays silent about the night during the day', () => {
    atHour(14);
    render({ messages: [] });

    expect(screen.queryByText('chat.empty_state.night_note')).not.toBeInTheDocument();
  });
});

describe('ChatMessageList — rendering the conversation', () => {
  it('renders every message with its role', () => {
    const { container } = render({ messages: [user('u1'), assistant('a1')] });

    expect(screen.getByText('Bonjour')).toBeInTheDocument();
    expect(screen.getByText('Bonjour à vous')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-message-role="user"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-message-role="assistant"]')).toHaveLength(1);
  });

  it('shows the typing bubble only while the assistant is composing', () => {
    const { unmount } = render({ messages: [user('u1')], isTyping: true });
    expect(screen.getByRole('status')).toBeInTheDocument();
    unmount();

    render({ messages: [user('u1')], isTyping: false });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('marks only the last assistant row as the latest one', () => {
    const { container } = render({
      messages: [assistant('a1'), user('u1'), assistant('a2')],
    });

    // Both assistant rows are present; the flag is what differs (spec D-5:
    // at most one looping emoji on screen).
    expect(container.querySelectorAll('[data-message-role="assistant"]')).toHaveLength(2);
    expect(container.querySelector('[data-message-id="a2"]')).not.toBeNull();
  });
});

describe('ChatMessageList — loading older history', () => {
  const messages = [user('u1'), assistant('a1')];

  it('does not watch for older history when there is none', () => {
    render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: false });

    expect(FakeIntersectionObserver.instances).toHaveLength(0);
  });

  it('does not watch when the parent offers no loader', () => {
    render({ messages, hasMoreOlder: true });

    expect(FakeIntersectionObserver.instances).toHaveLength(0);
  });

  it('asks for older messages when the top of the list comes into view', () => {
    const onLoadOlder = vi.fn();
    render({ messages, onLoadOlder, hasMoreOlder: true });

    expect(lastObserver().observed).toHaveLength(1);
    lastObserver().trigger(true);

    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });

  it('stays quiet while the sentinel is out of view', () => {
    const onLoadOlder = vi.fn();
    render({ messages, onLoadOlder, hasMoreOlder: true });

    lastObserver().trigger(false);

    expect(onLoadOlder).not.toHaveBeenCalled();
  });

  it('never fires a second request while one is already in flight', () => {
    const onLoadOlder = vi.fn();
    render({ messages, onLoadOlder, hasMoreOlder: true, isLoadingOlder: true });

    lastObserver().trigger(true);

    // Scrolling near the top would otherwise fire a burst of duplicates.
    expect(onLoadOlder).not.toHaveBeenCalled();
  });

  it('announces the fetch while older messages load', () => {
    render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: true, isLoadingOlder: true });

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('chat.loading_older_messages');
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('watches the list itself, with a margin so the fetch starts before the top', () => {
    render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: true });

    expect(lastObserver().options?.rootMargin).toBe('200px 0px 0px 0px');
    expect(lastObserver().options?.root).not.toBeNull();
  });

  it('stops watching when the conversation unmounts', () => {
    const { unmount } = render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: true });
    const observer = lastObserver();

    unmount();

    expect(observer.disconnected).toBe(true);
  });

  it('stops watching once the history is exhausted', () => {
    const onLoadOlder = vi.fn();
    const { rerender } = renderWithProviders(
      <ChatMessageList messages={messages} onLoadOlder={onLoadOlder} hasMoreOlder />
    );
    const observer = lastObserver();

    rerender(
      <ChatMessageList messages={messages} onLoadOlder={onLoadOlder} hasMoreOlder={false} />
    );

    expect(observer.disconnected).toBe(true);
  });
});

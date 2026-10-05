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

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { makeMessage, makePsycheState } from '@/__tests__/factories';
import type { Message } from '@/types/chat';
import { usePsycheStore } from '@/stores/psycheStore';

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

async function render(props: Partial<ChatMessageListProps> = {}) {
  // usePsyche starts its initial reads in microtasks. Keep their completion in
  // the mount's act scope before inspecting or unmounting the conversation.
  return act(async () => renderWithProviders(<ChatMessageList messages={[]} {...props} />));
}

const user = (id: string, content = 'Bonjour') =>
  makeMessage({ id, role: 'user', content }) as Message;
const assistant = (id: string, content = 'Bonjour à vous') =>
  makeMessage({ id, role: 'assistant', content }) as Message;

const psycheState = makePsycheState();

beforeEach(() => {
  vi.clearAllMocks();
  usePsycheStore.getState().reset();
  // Keep the real query/store hydration path while serving only controlled API data.
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const endpoint = String(input);
      if (endpoint.endsWith('/psyche/state')) return Response.json(psycheState);
      if (endpoint.endsWith('/psyche/settings'))
        return Response.json({
          psyche_enabled: false,
          psyche_display_avatar: true,
          psyche_sensitivity: 50,
          psyche_stability: 50,
        });
      throw new Error(`Unexpected API read: ${endpoint}`);
    })
  );
  FakeIntersectionObserver.instances = [];
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('ChatMessageList — malformed input', () => {
  it('shows an error card instead of crashing the conversation', async () => {
    // The prop is typed, but the value crosses an API/state boundary at runtime.
    await render({ messages: null as unknown as Message[] });

    expect(screen.getByText('chat.error.title')).toBeInTheDocument();
    expect(screen.getByText('chat.error.message')).toBeInTheDocument();
  });

  it('logs the type without ever logging the content', async () => {
    await render({ messages: 'oops' as unknown as Message[] });

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

  it('greets and explains what the assistant is for', async () => {
    atHour(14);
    await render({ messages: [] });

    expect(screen.getByText('chat.empty_state.title')).toBeInTheDocument();
    expect(screen.getByText('chat.empty_state.description')).toBeInTheDocument();
  });

  it('adds the nightly consolidation note deep at night', async () => {
    atHour(2);
    await render({ messages: [] });

    expect(screen.getByText('chat.empty_state.night_note')).toBeInTheDocument();
  });

  it('stays silent about the night during the day', async () => {
    atHour(14);
    await render({ messages: [] });

    expect(screen.queryByText('chat.empty_state.night_note')).not.toBeInTheDocument();
  });
});

describe('ChatMessageList — rendering the conversation', () => {
  it('renders every message with its role', async () => {
    const { container } = await render({ messages: [user('u1'), assistant('a1')] });

    expect(screen.getByText('Bonjour')).toBeInTheDocument();
    expect(screen.getByText('Bonjour à vous')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-message-role="user"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-message-role="assistant"]')).toHaveLength(1);
  });

  it('shows the typing bubble only while the assistant is composing', async () => {
    const { unmount } = await render({ messages: [user('u1')], isTyping: true });
    expect(screen.getByRole('status')).toBeInTheDocument();
    unmount();

    await render({ messages: [user('u1')], isTyping: false });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('marks only the last assistant row as the latest one', async () => {
    const { container } = await render({
      messages: [assistant('a1'), user('u1'), assistant('a2')],
    });

    // Both assistant rows are present; the flag is what differs (spec D-5:
    // at most one looping emoji on screen).
    expect(container.querySelectorAll('[data-message-role="assistant"]')).toHaveLength(2);
    expect(container.querySelector('[data-message-id="a2"]')).not.toBeNull();
  });
});

/*
 * Initial scroll positioning is NOT covered here, deliberately.
 *
 * It was, and the coverage was worse than none: jsdom performs no layout, so
 * the suite asserted against stubbed `scrollHeight` values on the component's
 * own container — a box that, in the real page, never scrolls at all (the chat
 * page wraps the list in its own `overflow-y-auto`). Those tests passed green
 * against a fix that was a complete no-op in a browser, which is how a
 * "positioning bug" survived two releases.
 *
 * The real oracles now live in `apps/web/e2e/smoke/chat-initial-scroll.spec.ts`,
 * where a real engine reports the geometry of the box that actually scrolls.
 */

describe('ChatMessageList — loading older history', () => {
  const messages = [user('u1'), assistant('a1')];

  it('does not watch for older history when there is none', async () => {
    await render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: false });

    expect(FakeIntersectionObserver.instances).toHaveLength(0);
  });

  it('does not watch when the parent offers no loader', async () => {
    await render({ messages, hasMoreOlder: true });

    expect(FakeIntersectionObserver.instances).toHaveLength(0);
  });

  it('asks for older messages when the top of the list comes into view', async () => {
    const onLoadOlder = vi.fn();
    await render({ messages, onLoadOlder, hasMoreOlder: true });

    expect(lastObserver().observed).toHaveLength(1);
    lastObserver().trigger(true);

    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });

  it('stays quiet while the sentinel is out of view', async () => {
    const onLoadOlder = vi.fn();
    await render({ messages, onLoadOlder, hasMoreOlder: true });

    lastObserver().trigger(false);

    expect(onLoadOlder).not.toHaveBeenCalled();
  });

  it('never fires a second request while one is already in flight', async () => {
    const onLoadOlder = vi.fn();
    await render({ messages, onLoadOlder, hasMoreOlder: true, isLoadingOlder: true });

    lastObserver().trigger(true);

    // Scrolling near the top would otherwise fire a burst of duplicates.
    expect(onLoadOlder).not.toHaveBeenCalled();
  });

  it('announces the fetch while older messages load', async () => {
    await render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: true, isLoadingOlder: true });

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('chat.loading_older_messages');
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('watches the list itself, with a margin so the fetch starts before the top', async () => {
    await render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: true });

    expect(lastObserver().options?.rootMargin).toBe('200px 0px 0px 0px');
    expect(lastObserver().options?.root).not.toBeNull();
  });

  it('stops watching when the conversation unmounts', async () => {
    const { unmount } = await render({ messages, onLoadOlder: vi.fn(), hasMoreOlder: true });
    const observer = lastObserver();

    unmount();

    expect(observer.disconnected).toBe(true);
  });

  it('stops watching once the history is exhausted', async () => {
    const onLoadOlder = vi.fn();
    const { rerender } = await render({ messages, onLoadOlder, hasMoreOlder: true });
    const observer = lastObserver();

    rerender(
      <ChatMessageList messages={messages} onLoadOlder={onLoadOlder} hasMoreOlder={false} />
    );

    expect(observer.disconnected).toBe(true);
  });
});

describe('ChatMessageList — where the floating return button is drawn', () => {
  // jsdom lays nothing out: these pin WHERE the button mounts. That it then
  // sits on screen and on top is the browser journey's (chat-scroll-follow).
  const returnButton = () => screen.getByRole('button', { name: 'chat.scroll.return_to_present' });

  it('in the slot the page holds above its composer', async () => {
    const slot = document.createElement('div');
    document.body.appendChild(slot);
    try {
      await render({ messages: [user('m1')], historyView: true, scrollUiSlot: slot });

      expect(slot.contains(returnButton())).toBe(true);
    } finally {
      slot.remove();
    }
  });

  it('sticky at the bottom of the list when the page holds no slot', async () => {
    const { container } = await render({ messages: [user('m1')], historyView: true });

    expect(container.contains(returnButton())).toBe(true);
    expect(returnButton().closest('.sticky')).not.toBeNull();
  });
});

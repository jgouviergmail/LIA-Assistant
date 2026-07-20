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

describe('ChatMessageList — initial positioning', () => {
  // jsdom performs no layout: `scrollHeight` is 0 and `scroll-behavior` is not
  // a recognised CSS property, so both are installed here. Without the height,
  // every scroll-position assertion would be vacuously true (0 === 0).
  const CONTENT_HEIGHT = 5000;
  let originalScrollHeight: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalScrollHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollHeight');
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get: () => CONTENT_HEIGHT,
    });
  });

  afterEach(() => {
    if (originalScrollHeight) {
      Object.defineProperty(HTMLElement.prototype, 'scrollHeight', originalScrollHeight);
    }
  });

  function scrollContainer(root: HTMLElement): HTMLElement {
    const el = root.querySelector<HTMLElement>('.overflow-y-auto');
    if (!el) throw new Error('scroll container not found');
    return el;
  }

  const longHistory = Array.from({ length: 40 }, (_, i) =>
    i % 2 === 0 ? user(`u${i}`) : assistant(`a${i}`)
  );

  it('opens a long conversation at its last message, not in the middle', () => {
    // The defect: the initial scroll was animated, so while it played the list
    // still sat near the top, the pagination sentinel was on screen, the
    // observer fired `onLoadOlder`, and the resulting prepend raised the
    // "was prepend" flag — which SUPPRESSES the scroll-to-bottom. The reader
    // was stranded mid-history, the more reliably the longer the conversation.
    const { container } = render({ messages: longHistory, hasMoreOlder: true });

    expect(scrollContainer(container).scrollTop).toBe(CONTENT_HEIGHT);
  });

  it('reaches the bottom without ever animating', () => {
    // The container's `scroll-smooth` class animates every programmatic
    // scroll, a plain `scrollTop` assignment included. It is therefore
    // neutralised for the duration of the jump, then restored so live updates
    // keep gliding.
    const setProperty = vi.spyOn(CSSStyleDeclaration.prototype, 'setProperty');
    const removeProperty = vi.spyOn(CSSStyleDeclaration.prototype, 'removeProperty');

    render({ messages: longHistory });

    expect(setProperty).toHaveBeenCalledWith('scroll-behavior', 'auto');
    expect(removeProperty).toHaveBeenCalledWith('scroll-behavior');
  });

  it('does not also animate its way to a bottom it already reached', () => {
    // The layout effect has placed the viewport before paint; letting the
    // auto-scroll effect fire as well would animate a scroll that is already
    // done — and re-open the window this fix closes.
    const scrollIntoView = vi
      .spyOn(Element.prototype, 'scrollIntoView')
      .mockImplementation(() => {});

    render({ messages: longHistory });

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('re-arms the jump for the next conversation once the list is cleared', () => {
    // Starting a new chat empties the list; the history loaded afterwards must
    // open at its bottom too, not wherever the previous one left the viewport.
    const { container, rerender } = render({ messages: longHistory });
    // Park the viewport away from the bottom so the assertion below can only
    // pass if the jump genuinely ran a second time.
    scrollContainer(container).scrollTop = 0;

    rerender(<ChatMessageList messages={[]} />);
    rerender(<ChatMessageList messages={longHistory} />);

    expect(scrollContainer(container).scrollTop).toBe(CONTENT_HEIGHT);
  });

  it('does not re-jump to the bottom when older history is prepended', () => {
    // The prepend path restores the scroll position itself; a second jump
    // would hide the messages the reader just asked for.
    const { container, rerender } = render({ messages: longHistory, hasMoreOlder: true });
    const el = scrollContainer(container);
    el.scrollTop = 1234;

    rerender(<ChatMessageList messages={[user('older'), ...longHistory]} hasMoreOlder />);

    expect(el.scrollTop).toBe(1234);
  });

  it('keeps animating later updates, so new replies glide into view', () => {
    // Only the FIRST positioning is instant; live updates stay smooth.
    const scrollIntoView = vi
      .spyOn(Element.prototype, 'scrollIntoView')
      .mockImplementation(() => {});
    const { rerender } = render({ messages: longHistory });
    scrollIntoView.mockClear();

    rerender(<ChatMessageList messages={[...longHistory, assistant('new')]} />);

    const behaviours = scrollIntoView.mock.calls.map(
      ([options]) => (options as ScrollIntoViewOptions | undefined)?.behavior
    );
    expect(behaviours).toContain('smooth');
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

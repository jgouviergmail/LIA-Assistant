/**
 * useNotifications — the SSE channel every proactive signal rides on.
 *
 * The `EventSource` is replaced by a controllable fake, so the properties that
 * only show up in the field are driven explicitly here:
 *
 *  - a dropped connection **reconnects with a growing delay**, and gives up
 *    after a bounded number of attempts instead of hammering the server;
 *  - the same notification arriving twice (SSE retry, FCM duplicate) is
 *    counted once, and the backlog is capped;
 *  - logging out or unmounting closes the stream **and** cancels a pending
 *    reconnect — a timer that survives would reopen a stream for a user who
 *    is no longer there.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
const { onForegroundMessage } = vi.hoisted(() => ({ onForegroundMessage: vi.fn(() => vi.fn()) }));
vi.mock('@/lib/firebase', () => ({ onForegroundMessage }));

import { useNotifications, routeNotification } from '../useNotifications';
import type { Notification } from '@/hooks/useNotifications';

/** A controllable EventSource: the test decides when it opens, fails, emits. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;
  closed = false;
  private listeners = new Map<string, (event: MessageEvent) => void>();

  constructor(
    readonly url: string,
    readonly init?: { withCredentials?: boolean }
  ) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    this.listeners.set(type, handler);
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }

  /** Delivers a payload on the named SSE event, as the backend does. */
  emit(data: unknown, type = 'notification') {
    const handler = type === 'message' ? this.onmessage : this.listeners.get(type);
    handler?.({ data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent);
  }

  fail() {
    this.onerror?.(new Event('error'));
  }
}

const live = () => FakeEventSource.instances[FakeEventSource.instances.length - 1];

function setup(over: Parameters<typeof useNotifications>[0] = {}) {
  return renderHook(() =>
    useNotifications({ isAuthenticated: true, enableSSE: true, enableFCM: false, ...over })
  );
}

/** Opens the stream and hands back the live fake. */
function connected(over: Parameters<typeof useNotifications>[0] = {}) {
  const hook = setup(over);
  act(() => live().onopen?.());
  return { ...hook, source: live() };
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('useNotifications — connection lifecycle', () => {
  it('opens an authenticated stream on the notifications endpoint', () => {
    const { result } = connected();

    expect(live().url).toMatch(/\/api\/v1\/notifications\/stream$/);
    expect(live().init?.withCredentials).toBe(true);
    expect(result.current.isConnected).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it('stays offline while the user is not authenticated', () => {
    const { result } = setup({ isAuthenticated: false });

    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.isConnected).toBe(false);
  });

  it('stays offline when the channel is disabled', () => {
    setup({ enableSSE: false });

    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('closes the stream when the user logs out', () => {
    const { rerender } = renderHook(
      ({ isAuthenticated }) =>
        useNotifications({ isAuthenticated, enableSSE: true, enableFCM: false }),
      { initialProps: { isAuthenticated: true } }
    );
    const source = live();

    rerender({ isAuthenticated: false });

    expect(source.closed).toBe(true);
  });

  it('closes the stream on unmount', () => {
    const { unmount } = connected();
    const source = live();

    unmount();

    expect(source.closed).toBe(true);
  });
});

describe('useNotifications — reconnection', () => {
  beforeEach(() => vi.useFakeTimers());

  it('reopens the stream after a growing delay', () => {
    const { result } = connected();

    act(() => live().fail());
    expect(result.current.isConnected).toBe(false);
    expect(FakeEventSource.instances).toHaveLength(1);

    // First attempt after one delay unit.
    act(() => void vi.advanceTimersByTime(3_000));
    expect(FakeEventSource.instances).toHaveLength(2);

    // The second retry waits longer than the first: 2 × 3 s.
    act(() => live().fail());
    act(() => void vi.advanceTimersByTime(3_000));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => void vi.advanceTimersByTime(3_000));
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it('gives up after the bounded number of attempts and says so', () => {
    const { result } = connected();

    for (let attempt = 1; attempt <= 5; attempt++) {
      act(() => live().fail());
      act(() => void vi.advanceTimersByTime(3_000 * attempt));
    }
    // The sixth failure exhausts the budget.
    act(() => live().fail());
    act(() => void vi.advanceTimersByTime(120_000));

    expect(FakeEventSource.instances).toHaveLength(6);
    expect(result.current.error).toMatch(/refresh the page/i);
  });

  it('resets the attempt budget once a connection succeeds again', () => {
    connected();

    act(() => live().fail());
    act(() => void vi.advanceTimersByTime(3_000));
    act(() => live().onopen?.());

    // Back to a first-attempt delay, not the escalated one.
    act(() => live().fail());
    act(() => void vi.advanceTimersByTime(3_000));
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it('cancels a pending reconnect when the user leaves', () => {
    const { unmount } = connected();

    act(() => live().fail());
    unmount();
    act(() => void vi.advanceTimersByTime(60_000));

    // A surviving timer would open a stream for a user who is gone.
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});

describe('useNotifications — incoming notifications', () => {
  it('keeps the newest first and counts it as unread', () => {
    const { result } = connected();

    act(() => live().emit({ type: 'reminder', reminder_id: 'r1', content: 'Appeler Marie' }));
    act(() => live().emit({ type: 'system', content: 'Maintenance' }));

    expect(result.current.notifications[0].content).toBe('Maintenance');
    expect(result.current.unreadCount).toBe(2);
  });

  it('ignores a duplicate id (an SSE retry must not double the badge)', () => {
    const { result } = connected();
    const payload = { type: 'reminder', reminder_id: 'r1', content: 'Appeler Marie' };

    act(() => live().emit(payload));
    act(() => live().emit(payload));

    expect(result.current.notifications).toHaveLength(1);
  });

  it('caps the backlog at fifty', () => {
    const { result } = connected();

    act(() => {
      for (let i = 0; i < 60; i++) {
        live().emit({ type: 'system', target_id: `n${i}`, content: `#${i}` });
      }
    });

    expect(result.current.notifications).toHaveLength(50);
    expect(result.current.notifications[0].content).toBe('#59');
  });

  it('accepts the default message event as well as the named one', () => {
    const { result } = connected();

    act(() => live().emit({ type: 'system', target_id: 'x', content: 'fallback' }, 'message'));

    expect(result.current.notifications).toHaveLength(1);
  });

  it('rebuilds the metadata a scheduled action sends flat', () => {
    const { result } = connected();

    act(() =>
      live().emit({
        type: 'scheduled_action',
        action_id: 'sa-1',
        title: 'Briefing',
        content: 'Terminé',
      })
    );

    expect(result.current.notifications[0]).toMatchObject({
      id: 'sa-1',
      metadata: { type: 'scheduled_action', action_id: 'sa-1', title: 'Briefing' },
    });
  });

  it('falls back through the id fields the backends use', () => {
    const { result } = connected();

    act(() => live().emit({ type: 'oauth_health_warning', connector_id: 'c-9', content: 'Token' }));

    expect(result.current.notifications[0].id).toBe('c-9');
  });

  it('survives a payload it cannot parse', () => {
    const { result } = connected();

    act(() => live().emit('{not json'));

    expect(result.current.notifications).toHaveLength(0);
    expect(result.current.isConnected).toBe(true);
  });

  it('hands every notification to the generic callback', () => {
    const onNotification = vi.fn();
    connected({ onNotification });

    act(() => live().emit({ type: 'system', target_id: 'x', content: 'hello' }));

    expect(onNotification).toHaveBeenCalledWith(expect.objectContaining({ content: 'hello' }));
  });
});

describe('useNotifications — reading state', () => {
  it('marks one notification as read', () => {
    const { result } = connected();
    act(() => live().emit({ type: 'reminder', reminder_id: 'r1', content: 'a' }));
    act(() => live().emit({ type: 'reminder', reminder_id: 'r2', content: 'b' }));

    act(() => result.current.markAsRead('r1'));

    expect(result.current.unreadCount).toBe(1);
    expect(result.current.notifications.find(n => n.id === 'r1')?.read).toBe(true);
  });

  it('marks everything as read', () => {
    const { result } = connected();
    act(() => live().emit({ type: 'reminder', reminder_id: 'r1', content: 'a' }));
    act(() => live().emit({ type: 'reminder', reminder_id: 'r2', content: 'b' }));

    act(() => result.current.markAllAsRead());

    expect(result.current.unreadCount).toBe(0);
  });

  it('clears the backlog', () => {
    const { result } = connected();
    act(() => live().emit({ type: 'reminder', reminder_id: 'r1', content: 'a' }));

    act(() => result.current.clearNotifications());

    expect(result.current.notifications).toEqual([]);
  });
});

describe('routeNotification', () => {
  function notification(over: Partial<Notification> = {}): Notification {
    return {
      id: 'n1',
      type: 'system',
      content: 'hello',
      timestamp: new Date('2026-07-19T10:00:00Z'),
      read: false,
      ...over,
    };
  }

  it('routes the whole proactive family by prefix', () => {
    const onProactiveNotification = vi.fn();

    routeNotification(
      notification({ type: 'proactive_heartbeat', target_id: 't-1', metadata: { a: 1 } }),
      { onProactiveNotification }
    );

    expect(onProactiveNotification).toHaveBeenCalledWith('hello', 't-1', { a: 1 });
  });

  it('ignores a proactive notification with no target', () => {
    const onProactiveNotification = vi.fn();

    routeNotification(notification({ type: 'proactive_interest' }), { onProactiveNotification });

    expect(onProactiveNotification).not.toHaveBeenCalled();
  });

  it('routes a reminder to its own handler', () => {
    const onReminder = vi.fn();
    const onProactiveNotification = vi.fn();

    routeNotification(notification({ type: 'reminder', reminder_id: 'r-1' }), {
      onReminder,
      onProactiveNotification,
    });

    expect(onReminder).toHaveBeenCalled();
    expect(onProactiveNotification).not.toHaveBeenCalled();
  });

  it('does nothing for a type nobody listens to', () => {
    const onReminder = vi.fn();

    expect(() =>
      routeNotification(notification({ type: 'message' }), { onReminder })
    ).not.toThrow();
    expect(onReminder).not.toHaveBeenCalled();
  });
});

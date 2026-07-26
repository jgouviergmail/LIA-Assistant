/**
 * BroadcastProvider — admin announcements, which arrive through three doors at
 * once (an unread fetch, an SSE stream, an FCM push) and must land as **one**
 * modal per announcement.
 *
 * The properties that matter:
 *  - the same broadcast arriving twice (SSE + FCM, or a re-fetch) is shown once;
 *  - **multi-tab sync**: when another tab displays an announcement, this tab
 *    drops it from its own queue instead of showing it again;
 *  - the unread check is **debounced**, so returning to the tab repeatedly does
 *    not hammer the endpoint;
 *  - nothing at all happens while the user is logged out — no stream, no fetch;
 *  - dismissing marks the announcement read **and** moves to the next one, even
 *    if the read call fails (the user has seen it either way).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useContext } from 'react';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const { onForegroundMessage, fcmHandler } = vi.hoisted(() => {
  const holder: { current: ((payload: unknown) => void) | null } = { current: null };
  return {
    fcmHandler: holder,
    onForegroundMessage: vi.fn((handler: (payload: unknown) => void) => {
      holder.current = handler;
      return vi.fn();
    }),
  };
});
vi.mock('@/lib/firebase', () => ({ onForegroundMessage }));

import { BroadcastProvider, BroadcastContext, type BroadcastInfo } from '../broadcast';

/** A controllable BroadcastChannel: the test plays the "other tab". */
class FakeChannel {
  static instances: FakeChannel[] = [];

  onmessage: ((event: { data: { type: string; broadcastId: string } }) => void) | null = null;
  posted: unknown[] = [];
  closed = false;

  constructor(readonly name: string) {
    FakeChannel.instances.push(this);
  }

  postMessage(data: unknown) {
    this.posted.push(data);
  }

  close() {
    this.closed = true;
  }
}

/** A controllable EventSource, as in the notifications suite. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, (event: MessageEvent) => void>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    this.listeners.set(type, handler);
  }

  close() {
    this.closed = true;
  }

  emit(data: unknown) {
    this.listeners.get('notification')?.({
      data: typeof data === 'string' ? data : JSON.stringify(data),
    } as MessageEvent);
  }
}

const fetchMock = vi.fn();

function broadcast(over: Partial<BroadcastInfo> = {}): BroadcastInfo {
  return {
    id: 'b1',
    message: 'Maintenance ce soir',
    sent_at: '2026-07-19T10:00:00Z',
    ...over,
  };
}

function unreadResponse(broadcasts: BroadcastInfo[]) {
  // With the content-type a real backend always sends: `apiClient` only parses
  // a body it was told is JSON.
  return new Response(JSON.stringify({ broadcasts }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function setup(isAuthenticated = true) {
  return renderHook(() => useContext(BroadcastContext), {
    wrapper: ({ children }) => (
      <BroadcastProvider isAuthenticated={isAuthenticated}>{children}</BroadcastProvider>
    ),
  });
}

const channel = () => FakeChannel.instances[FakeChannel.instances.length - 1];
const stream = () => FakeEventSource.instances[FakeEventSource.instances.length - 1];

beforeEach(() => {
  vi.clearAllMocks();
  FakeChannel.instances = [];
  FakeEventSource.instances = [];
  fcmHandler.current = null;
  fetchMock.mockResolvedValue(unreadResponse([]));
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('BroadcastChannel', FakeChannel);
  vi.stubGlobal('EventSource', FakeEventSource);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('BroadcastProvider — while logged out', () => {
  it('opens no stream and asks for nothing', async () => {
    setup(false);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(0));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onForegroundMessage).not.toHaveBeenCalled();
  });
});

describe('BroadcastProvider — unread announcements', () => {
  it('asks for the unread list with the session cookie and shows the first one', async () => {
    fetchMock.mockResolvedValue(unreadResponse([broadcast(), broadcast({ id: 'b2' })]));
    const { result } = setup();

    await waitFor(() => expect(result.current?.showModal).toBe(true));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/notifications\/broadcasts\/unread$/);
    expect(init).toMatchObject({ credentials: 'include' });
    expect(result.current?.currentBroadcast?.id).toBe('b1');
    expect(result.current?.queueLength).toBe(2);
  });

  it('shows nothing when there is nothing to show', async () => {
    const { result } = setup();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(result.current?.showModal).toBe(false);
    expect(result.current?.currentBroadcast).toBeNull();
  });

  it('survives an endpoint that refuses', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }));
    const { result } = setup();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(result.current?.showModal).toBe(false);
  });

  it('survives an endpoint that is unreachable', async () => {
    fetchMock.mockRejectedValue(new Error('offline'));
    const { result } = setup();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(result.current?.showModal).toBe(false);
  });
});

describe('BroadcastProvider — debounce', () => {
  it('does not re-ask when the tab comes back right away', async () => {
    setup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Returning to the tab within the debounce window must not hammer the API.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('re-asks once the short visibility window has passed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await act(async () => {
      vi.advanceTimersByTime(11_000);
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('stops listening for visibility when it unmounts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { unmount } = setup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(60_000);
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('BroadcastProvider — live arrivals', () => {
  it('queues an announcement pushed over SSE', async () => {
    const { result } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    act(() => stream().emit({ type: 'admin_broadcast', broadcast_id: 'b9', message: 'Coupure' }));

    await waitFor(() => expect(result.current?.currentBroadcast?.id).toBe('b9'));
    expect(result.current?.currentBroadcast?.message).toBe('Coupure');
  });

  it.each([
    ['another notification type', { type: 'reminder', broadcast_id: 'b9' }],
    ['an announcement with no id', { type: 'admin_broadcast', message: 'x' }],
  ])('ignores %s', async (_label, payload) => {
    const { result } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    act(() => stream().emit(payload));

    await waitFor(() => expect(result.current?.queueLength).toBe(0));
  });

  it('survives an unparsable SSE frame', async () => {
    const { result } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    act(() => stream().emit('{not json'));

    expect(result.current?.queueLength).toBe(0);
  });

  it('queues an announcement pushed over FCM, preferring the notification body', async () => {
    const { result } = setup();
    await waitFor(() => expect(onForegroundMessage).toHaveBeenCalled());

    act(() =>
      fcmHandler.current?.({
        data: { type: 'admin_broadcast', broadcast_id: 'b8', message: 'depuis data' },
        notification: { body: 'depuis notification' },
      })
    );

    await waitFor(() => expect(result.current?.currentBroadcast?.id).toBe('b8'));
    expect(result.current?.currentBroadcast?.message).toBe('depuis notification');
  });

  it('falls back to the data message when the push carries no body', async () => {
    const { result } = setup();
    await waitFor(() => expect(onForegroundMessage).toHaveBeenCalled());

    act(() =>
      fcmHandler.current?.({
        data: { type: 'admin_broadcast', broadcast_id: 'b7', message: 'depuis data' },
      })
    );

    await waitFor(() => expect(result.current?.currentBroadcast?.message).toBe('depuis data'));
  });

  it('shows the same announcement once, however many doors it comes through', async () => {
    const { result } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    act(() => stream().emit({ type: 'admin_broadcast', broadcast_id: 'b5', message: 'Une fois' }));
    await waitFor(() => expect(result.current?.queueLength).toBe(1));
    act(() =>
      fcmHandler.current?.({
        data: { type: 'admin_broadcast', broadcast_id: 'b5', message: 'Une fois' },
      })
    );

    await waitFor(() => expect(result.current?.queueLength).toBe(1));
  });
});

describe('BroadcastProvider — multi-tab sync', () => {
  it('tells the other tabs which announcement it is showing', async () => {
    fetchMock.mockResolvedValue(unreadResponse([broadcast()]));
    const { result } = setup();

    await waitFor(() => expect(result.current?.showModal).toBe(true));
    expect(channel().name).toBe('admin_broadcasts');
    expect(channel().posted).toContainEqual({ type: 'broadcast_shown', broadcastId: 'b1' });
  });

  it('drops an announcement another tab has already shown', async () => {
    const { result } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => stream().emit({ type: 'admin_broadcast', broadcast_id: 'b3', message: 'Info' }));
    await waitFor(() => expect(result.current?.queueLength).toBe(1));

    act(() => channel().onmessage?.({ data: { type: 'broadcast_shown', broadcastId: 'b3' } }));

    await waitFor(() => expect(result.current?.queueLength).toBe(0));
  });

  it('ignores a message it does not understand', async () => {
    const { result } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => stream().emit({ type: 'admin_broadcast', broadcast_id: 'b4', message: 'Info' }));
    await waitFor(() => expect(result.current?.queueLength).toBe(1));

    act(() => channel().onmessage?.({ data: { type: 'autre', broadcastId: 'b4' } }));

    expect(result.current?.queueLength).toBe(1);
  });
});

describe('BroadcastProvider — dismissing', () => {
  it('marks it read and moves on to the next one', async () => {
    fetchMock.mockResolvedValue(unreadResponse([broadcast(), broadcast({ id: 'b2' })]));
    const { result } = setup();
    await waitFor(() => expect(result.current?.currentBroadcast?.id).toBe('b1'));

    await act(async () => {
      await result.current?.handleDismiss();
    });

    const read = fetchMock.mock.calls.find(([url]) => String(url).includes('/b1/read'));
    expect(read?.[1]).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(result.current?.currentBroadcast?.id).toBe('b2');
  });

  it('moves on even if the read call fails', async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).includes('/read')
        ? Promise.reject(new Error('offline'))
        : Promise.resolve(unreadResponse([broadcast()]))
    );
    const { result } = setup();
    await waitFor(() => expect(result.current?.showModal).toBe(true));

    await act(async () => {
      await result.current?.handleDismiss();
    });

    // The user has seen it: keeping the modal up would be worse than a lost ack.
    expect(result.current?.showModal).toBe(false);
    expect(result.current?.currentBroadcast).toBeNull();
  });

  it('does nothing when there is nothing on screen', async () => {
    const { result } = setup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fetchMock.mockClear();

    await act(async () => {
      await result.current?.handleDismiss();
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('BroadcastProvider — cleanup', () => {
  it('closes the channel and the stream when it goes away', async () => {
    const { unmount } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const openChannel = channel();
    const openStream = stream();

    unmount();

    expect(openChannel.closed).toBe(true);
    expect(openStream.closed).toBe(true);
  });
});

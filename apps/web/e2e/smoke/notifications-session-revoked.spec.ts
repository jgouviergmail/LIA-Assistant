/**
 * Notifications journey — a device signed out elsewhere leaves the app (point 22).
 *
 * Hermetic: the person's real-time channel (`/notifications/stream`) is a
 * mocked SSE whose handler awaits a test-controlled gate, then closes with one
 * of the two events the API ends a stream with (`_closing_event` in
 * `domains/notifications/router.py`). Before the fix the page ignored
 * `session_revoked`: its EventSource reconnected into a 401 at every backoff
 * step, and the person stayed on a dashboard that could no longer load
 * anything. The risk of the fix is the opposite one — a closing that is not a
 * revocation (`superseded`: a newer tab took the slot) must never sign anyone
 * out.
 *
 * Why a browser test: the exit is a real navigation, driven by the native
 * EventSource of the chat page's two consumers (the conversation sync's
 * notification hook and the broadcast provider). Only a browser proves where
 * the page lands, and that it stays.
 */
import {
  test,
  expect,
  chatRoutes,
  waitForHydration,
  waitForMockGate,
  type MockRoute,
} from '../fixtures';

const NL = String.fromCharCode(10);
const CHAT = '/en/dashboard/chat';
/** Streams the chat page opens: the conversation sync's and the broadcasts'. */
const CHAT_STREAMS = 2;

/** The two closings the API writes, byte for byte. */
const SESSION_REVOKED =
  'event: session_revoked' + NL + 'data: {"reason": "session_revoked"}' + NL + NL;
const SUPERSEDED = 'event: superseded' + NL + 'data: {"reason": "newer_stream"}' + NL + NL;

interface StreamCounts {
  opened: number;
  closed: number;
  reopened: number;
}

/**
 * A stream route that holds every request until `gate` opens, then closes it
 * with `closing`; a stream opened after that stays idle (unanswered).
 */
function closingStream(gate: Promise<void>, closing: string, streams: StreamCounts): MockRoute {
  return {
    url: '**/api/v1/notifications/stream',
    handler: async (route, signal) => {
      if (streams.closed > 0) {
        streams.reopened += 1;
        return;
      }
      streams.opened += 1;
      if (!(await waitForMockGate(gate, signal))) return;
      streams.closed += 1;
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: closing });
    },
  };
}

test.describe('notification stream closings (point 22)', () => {
  test('a revoked session sends the page to the login, and it stays there', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const streams: StreamCounts = { opened: 0, closed: 0, reopened: 0 };
    await authenticate();
    await mockApi([...chatRoutes([]), closingStream(gate, SESSION_REVOKED, streams)]);

    await page.goto(CHAT);
    await waitForHydration(page);
    await expect.poll(() => streams.opened, { timeout: 30_000 }).toBe(CHAT_STREAMS);
    expect(new URL(page.url()).pathname).toBe(CHAT);

    // « Sign out this device », elsewhere: the next keepalive closes the stream.
    release();

    // Polled, never `waitForURL`: both consumers redirect, so the second
    // navigation supersedes the first (net::ERR_ABORTED) on the same URL.
    await expect(page).toHaveURL(/\/en\/login$/, { timeout: 30_000 });
    await expect(page.locator('input[type="email"]')).toBeVisible();
    // Nothing sends the page back: still on the login once it has settled.
    await page.waitForLoadState('networkidle');
    expect(new URL(page.url()).pathname).toBe('/en/login');
  });

  test('a stream another tab superseded is reopened, and the person stays', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const streams: StreamCounts = { opened: 0, closed: 0, reopened: 0 };
    await authenticate();
    await mockApi([...chatRoutes([]), closingStream(gate, SUPERSEDED, streams)]);

    await page.goto(CHAT);
    await waitForHydration(page);
    await expect.poll(() => streams.opened, { timeout: 30_000 }).toBe(CHAT_STREAMS);

    release();

    // The visible tab retakes a slot at once: a stream is opened again…
    await expect.poll(() => streams.reopened, { timeout: 30_000 }).toBeGreaterThan(0);
    // …and the page never left the chat.
    expect(new URL(page.url()).pathname).toBe(CHAT);
    await expect(page.locator('input[type="email"]')).toHaveCount(0);
  });
});

import type { Page } from '@playwright/test';

/**
 * Next development boot waits for its real initial HMR synchronization.
 * Relay only that fixed same-origin channel, without allowing browser API sockets
 * or proxy upgrades. Production/managed-server journeys have no development HMR.
 */
export async function installDevHmr(page: Page, baseURL: string | undefined): Promise<() => void> {
  if (!baseURL || process.env.E2E_MANAGED_SERVER !== '0') return () => {};
  const origin = new URL(baseURL);
  if (origin.protocol !== 'http:') return () => {};
  if (!['localhost', '127.0.0.1', '127.0.0.6', '127.0.0.7', '[::1]'].includes(origin.hostname))
    return () => {};
  const expected = new URL('/_next/hmr', origin);
  expected.protocol = 'ws:';
  const sockets = new Set<WebSocket>();
  let stopped = false;
  await page.routeWebSocket(
    url => url.origin === expected.origin && url.pathname === expected.pathname,
    route => {
      if (stopped) {
        void route.close().catch(() => {});
        return;
      }
      // The URL is selected by the fixture; no cookie, API path or arbitrary
      // browser-selected destination is forwarded by this bounded HMR relay.
      const upstreamUrl = new URL(expected);
      const id = new URL(route.url()).searchParams.get('id');
      if (id && id.length < 128) upstreamUrl.searchParams.set('id', id);
      const upstream = new WebSocket(upstreamUrl.href);
      upstream.binaryType = 'arraybuffer';
      sockets.add(upstream);
      const pending: (string | Uint8Array<ArrayBuffer>)[] = [];
      let closed = false;
      route.onMessage(message => {
        if (stopped || message.length > 1_048_576) return;
        const value = typeof message === 'string' ? message : new Uint8Array(message);
        if (upstream.readyState === WebSocket.OPEN) upstream.send(value);
        else if (pending.length < 16) pending.push(value);
      });
      upstream.addEventListener('open', () => {
        for (const message of pending) upstream.send(message);
        pending.length = 0;
      });
      upstream.addEventListener('message', event => {
        if (stopped || closed) return;
        if (typeof event.data === 'string') route.send(event.data);
        else if (event.data instanceof ArrayBuffer) route.send(Buffer.from(event.data));
      });
      upstream.addEventListener('error', () => {
        void route.close().catch(() => {});
      });
      upstream.addEventListener('close', () => {
        sockets.delete(upstream);
        if (!stopped) void route.close().catch(() => {});
      });
      route.onClose(() => {
        closed = true;
        upstream.close();
        sockets.delete(upstream);
      });
    }
  );
  return () => {
    stopped = true;
    for (const socket of sockets) socket.close();
    sockets.clear();
  };
}

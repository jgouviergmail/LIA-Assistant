/** Real authenticated transport for server load, independent of client drawing. */
import type { Page } from '@playwright/test';
import { WORLD } from '../../src/features/world/definition';

export async function enterNativeTransportPeer(page: Page, alias: string): Promise<void> {
  // A same-origin static document has normal cookies and WebSocket Origin but
  // no React scene. The measured user's device never renders peers' browsers.
  await page.goto('/robots.txt');
  await page.evaluate(
    async ({ alias, scene }) => {
      const response = await fetch('/api/v1/world/ticket', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias, consent: true }),
      });
      if (!response.ok) throw new Error('Native load-peer ticket refused');
      const ticket: unknown = await response.json();
      if (
        !ticket ||
        typeof ticket !== 'object' ||
        !('ticket' in ticket) ||
        typeof ticket.ticket !== 'string'
      )
        throw new Error('Invalid native load-peer ticket');
      const token = ticket.ticket;
      const url = new URL('/api/v1/world/ws', location.href);
      url.protocol = 'ws:';
      await new Promise<void>((resolve, reject) => {
        const socket = new WebSocket(url);
        let epoch: string | null = null;
        let heartbeat = 0;
        let admitted = false;
        const timeout = window.setTimeout(() => {
          socket.close();
          reject(new Error('Native load-peer admission timed out'));
        }, 15000);
        const send = (type: 'leave' | 'heartbeat' | 'takeover') => {
          if (epoch && socket.readyState === WebSocket.OPEN)
            socket.send(
              JSON.stringify({
                type,
                epoch,
                version: 1,
                ...(type === 'heartbeat' ? { visible: !document.hidden, active: false } : {}),
              })
            );
        };
        socket.addEventListener(
          'open',
          () =>
            socket.send(
              JSON.stringify({
                type: 'authenticate',
                version: 1,
                scene,
                ticket: token,
                resume: null,
              })
            ),
          { once: true }
        );
        socket.addEventListener('message', event => {
          const frame: unknown = JSON.parse(String(event.data));
          if (
            !frame ||
            typeof frame !== 'object' ||
            !('type' in frame) ||
            frame.type !== 'snapshot' ||
            !('epoch' in frame) ||
            typeof frame.epoch !== 'string'
          )
            return;
          epoch = frame.epoch;
          if ('status' in frame && frame.status === 'active' && 'controlling' in frame) {
            if (!frame.controlling) {
              send('takeover');
              return;
            }
            if (!admitted) {
              admitted = true;
              document.documentElement.dataset.worldNativePeer = 'active';
              clearTimeout(timeout);
              heartbeat = window.setInterval(() => send('heartbeat'), 10000);
              resolve();
            }
          }
        });
        socket.addEventListener('close', () => {
          document.documentElement.dataset.worldNativePeer = 'closed';
          clearTimeout(timeout);
          clearInterval(heartbeat);
          if (!admitted) reject(new Error('Native load-peer connection refused'));
        });
        window.addEventListener(
          'world-proof-leave',
          () => {
            clearInterval(heartbeat);
            send('leave');
            socket.close();
          },
          { once: true }
        );
      });
    },
    { alias, scene: `${WORLD.id}:${WORLD.version}` }
  );
}

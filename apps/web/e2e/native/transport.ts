import type { Page } from '@playwright/test';

declare global {
  interface Window {
    __liaWorldTransportFault?: { disconnect(): void };
  }
}

/** Keep native cookies, Origin and frames intact; only close the real socket. */
export function worldTransportFault() {
  let current: Page | null = null;
  let connections = 0;
  return {
    async install(page: Page) {
      current = page;
      page.on('websocket', socket => {
        if (new URL(socket.url()).pathname === '/api/v1/world/ws') connections++;
      });
      await page.addInitScript(() => {
        const NativeSocket = window.WebSocket;
        let channel: WebSocket | null = null;
        window.WebSocket = class extends NativeSocket {
          constructor(url: string | URL, protocols?: string | string[]) {
            super(url, protocols);
            if (new URL(url, location.href).pathname === '/api/v1/world/ws') channel = this;
          }
        };
        window.__liaWorldTransportFault = {
          disconnect() {
            if (!channel || channel.readyState !== NativeSocket.OPEN)
              throw new Error('Owned native channel is not open');
            channel.close(4000, 'inert reconnect qualification');
          },
        };
      });
    },
    connections: () => connections,
    async disconnect() {
      if (!current) throw new Error('Owned world transport is not connected');
      await current.evaluate(() => {
        if (!window.__liaWorldTransportFault) throw new Error('Missing native fault probe');
        window.__liaWorldTransportFault.disconnect();
      });
    },
  };
}

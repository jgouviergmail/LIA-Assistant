/** An HTTP transport boundary survives Chromium's detached keepalive sends. */
import { createServer, request as forwardHttp, type ClientRequest } from 'node:http';
import type { Socket } from 'node:net';
import { pipeline, type Duplex } from 'node:stream';

export interface ApiNetworkGuard {
  proxy: { server: string; bypass: string };
  blockedRequests: string[];
  quarantine: () => void;
  close: () => Promise<void>;
}

export async function createApiNetworkGuard(): Promise<ApiNetworkGuard> {
  let quarantined = false;
  const blockedRequests: string[] = [];
  const forwards = new Set<ClientRequest>();
  const sockets = new Set<Socket>();
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? '/', 'http://invalid-proxy-request');
    if (quarantined || url.protocol !== 'http:' || url.pathname.startsWith('/api/v1/')) {
      blockedRequests.push(`${request.method} ${url.href}`);
      response
        .writeHead(501, { 'Content-Type': 'application/json', Connection: 'close' })
        .end(JSON.stringify({ error: 'unmocked_api_call', method: request.method, url: url.href }));
      return;
    }
    const headers = { ...request.headers };
    delete headers['proxy-connection'];
    delete headers['proxy-authorization'];
    const forwarded = forwardHttp(url, { method: request.method, headers }, upstream => {
      response.writeHead(upstream.statusCode ?? 502, upstream.headers);
      pipeline(upstream, response, error => {
        if (error) response.destroy();
      });
    });
    forwards.add(forwarded);
    forwarded.once('close', () => forwards.delete(forwarded));
    forwarded.once('error', error => {
      if (!response.headersSent) response.writeHead(502, { Connection: 'close' });
      response.end(error.message);
    });
    request.once('aborted', () => forwarded.destroy());
    request.once('error', error => forwarded.destroy(error));
    response.once('close', () => forwarded.destroy());
    request.pipe(forwarded);
  });
  server.on('connection', socket => {
    sockets.add(socket);
    socket.once('close', () => sockets.delete(socket));
  });
  const rejectOpaqueTransport = (method: string, url: string | undefined, client: Duplex) => {
    client.once('error', () => client.destroy());
    blockedRequests.push(`${method} ${url}`);
    client.end('HTTP/1.1 501 Unmocked transport\r\nConnection: close\r\n\r\n');
  };
  server.on('connect', (request, client) => {
    rejectOpaqueTransport('CONNECT', request.url, client);
  });
  server.on('upgrade', (request, client) => {
    rejectOpaqueTransport('UPGRADE', request.url, client);
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Expected proxy TCP address');
  const quarantine = () => {
    quarantined = true;
    for (const forward of forwards) forward.destroy();
  };
  return {
    // Chromium bypasses loopback unless the implicit bypass is explicitly removed.
    proxy: { server: `http://127.0.0.1:${address.port}`, bypass: '<-loopback>' },
    blockedRequests,
    quarantine,
    close: async () => {
      quarantine();
      for (const socket of sockets) socket.destroy();
      await new Promise<void>((resolve, reject) => {
        server.close(error => (error ? reject(error) : resolve()));
      });
    },
  };
}

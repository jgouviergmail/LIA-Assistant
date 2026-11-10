/** An HTTP transport boundary survives Chromium's detached keepalive sends. */
import { createServer, request as forwardHttp, type ClientRequest } from 'node:http';
import type { Socket } from 'node:net';
import { pipeline, type Duplex } from 'node:stream';
import {
  createMultipartCapture,
  type MultipartCapture,
  type MultipartCaptureOptions,
  type OwnedMultipartCapture,
} from './multipart-upload';

export interface ApiNetworkGuard {
  proxy: { server: string; bypass: string };
  blockedRequests: string[];
  /** Receive one exact native upload on this guard's same-origin front door. */
  captureMultipartUpload: (options: MultipartCaptureOptions) => MultipartCapture;
  quarantine: () => void;
  close: () => Promise<void>;
}

function isApiPath(pathname: string): boolean {
  try {
    return /^\/api(?:\/|$)/i.test(decodeURIComponent(pathname));
  } catch {
    return true;
  }
}

function mustRefuse(
  url: URL,
  method: string | undefined,
  quarantined: boolean,
  origin: string,
  owned: OwnedMultipartCapture | undefined
): boolean {
  if (quarantined || url.protocol !== 'http:' || url.pathname.startsWith('/api/v1/')) return true;
  if (url.origin !== origin) return false;
  return !owned || !['GET', 'HEAD'].includes(method ?? '') || isApiPath(url.pathname);
}

export async function createApiNetworkGuard(): Promise<ApiNetworkGuard> {
  let quarantined = false;
  const blockedRequests: string[] = [];
  const forwards = new Set<ClientRequest>();
  const receptions = new Set<Promise<void>>();
  const sockets = new Set<Socket>();
  let origin = 'http://invalid-proxy-request';
  let upload: OwnedMultipartCapture | undefined;
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? '/', origin);
    const owned = upload && url.origin === origin ? upload : undefined;
    if (
      !quarantined &&
      owned &&
      request.method === 'POST' &&
      url.pathname === owned.pathname &&
      !url.search
    ) {
      const receiving = owned.receive(request, response).catch((error: unknown) => {
        owned.capture.errors.push(error instanceof Error ? error.message : String(error));
        response.destroy();
      });
      receptions.add(receiving);
      void receiving.then(() => receptions.delete(receiving));
      return;
    }
    if (mustRefuse(url, request.method, quarantined, origin, owned)) {
      blockedRequests.push(`${request.method} ${url.href}`);
      response
        .writeHead(501, { 'Content-Type': 'application/json', Connection: 'close' })
        .end(JSON.stringify({ error: 'unmocked_api_call', method: request.method, url: url.href }));
      return;
    }
    const headers = { ...request.headers };
    delete headers['proxy-connection'];
    delete headers['proxy-authorization'];
    const destination = owned ? new URL(url.pathname + url.search, owned.upstream) : url;
    const forwarded = forwardHttp(destination, { method: request.method, headers }, upstream => {
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
  origin = `http://127.0.0.1:${address.port}`;
  const quarantine = () => {
    quarantined = true;
    for (const forward of forwards) forward.destroy();
  };
  return {
    // Chromium bypasses loopback unless the implicit bypass is explicitly removed.
    proxy: { server: origin, bypass: '<-loopback>' },
    blockedRequests,
    captureMultipartUpload: options => {
      if (quarantined || upload) throw new Error('Upload capture is closed or already registered');
      upload = createMultipartCapture(origin, options);
      return upload.capture;
    },
    quarantine,
    close: async () => {
      quarantine();
      for (const socket of sockets) socket.destroy();
      await new Promise<void>((resolve, reject) => {
        server.close(error => (error ? reject(error) : resolve()));
      });
      await Promise.all(receptions);
    },
  };
}

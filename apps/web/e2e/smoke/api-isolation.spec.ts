/** The API boundary must remain hermetic while the browser closes its page. */
import { createServer, type Server } from 'node:http';
import { connect } from 'node:net';
import { test as appTest, expect, idleNotificationStream, waitForMockGate } from '../fixtures';

interface LocalServer {
  origin: string;
  escaped: string[];
  delayedCompleted: boolean;
  gateCancelled: boolean;
}

const test = appTest.extend<object, { localServer: LocalServer }>({
  localServer: [
    async ({ browserName }, provide) => {
      const escaped: string[] = [];
      const server = createServer((request, response) => {
        if (request.url?.startsWith('/api/v1/')) {
          escaped.push(`${request.method} ${request.url}`);
          response.writeHead(500).end('API request escaped the browser routes');
          return;
        }
        if (request.url === '/isolation-stream') {
          response.writeHead(200, { 'Content-Type': 'text/plain' });
          response.write('Stream remains open until the context quarantines it');
          return;
        }
        response.writeHead(200, { 'Content-Type': 'text/html' }).end('<h1>API isolation</h1>');
      });
      server.on('connect', (request, socket) => {
        escaped.push(`CONNECT ${request.url}`);
        socket.end('HTTP/1.1 500 Tunnel escaped\r\nConnection: close\r\n\r\n');
      });
      server.on('upgrade', (request, socket) => {
        escaped.push(`UPGRADE ${request.url}`);
        socket.end('HTTP/1.1 500 Upgrade escaped\r\nConnection: close\r\n\r\n');
      });
      await listen(server);
      const address = server.address();
      if (!address || typeof address === 'string') throw new Error('Expected a TCP server address');
      try {
        await provide({
          origin: `http://127.0.0.1:${address.port}`,
          escaped,
          delayedCompleted: false,
          gateCancelled: false,
        });
      } finally {
        await new Promise<void>((resolve, reject) => {
          server.close(error => (error ? reject(error) : resolve()));
        });
      }
      expect(
        escaped,
        `${browserName}: no API request may reach the server, including teardown`
      ).toEqual([]);
    },
    { scope: 'worker' },
  ],
});

test.describe.serial('callbacks finish in their owning test', () => {
  test('a deferred response finishes after the test body', async ({
    page,
    localServer,
    mockApi,
  }) => {
    let entered = false;
    await mockApi([
      {
        url: '**/api/v1/isolation/deferred',
        handler: async route => {
          entered = true;
          // Model the existing dashboard Radio fixture's four-second read.
          await new Promise(resolve => setTimeout(resolve, 4000));
          await route.fulfill({ json: { ready: true } });
          localServer.delayedCompleted = true;
        },
      },
    ]);
    await page.goto(localServer.origin);
    await page.evaluate(() => {
      void fetch('/api/v1/isolation/deferred').catch(() => undefined);
    });
    await expect.poll(() => entered).toBe(true);
    expect(localServer.delayedCompleted).toBe(false);
  });

  test('the following test sees completion and leaves an unreleased gate', async ({
    page,
    localServer,
    mockApi,
  }) => {
    expect(localServer.delayedCompleted).toBe(true);
    let entered = false;
    const gate = new Promise<void>(() => undefined);
    await mockApi([
      {
        url: '**/api/v1/isolation/unreleased',
        handler: async (route, signal) => {
          entered = true;
          if (!(await waitForMockGate(gate, signal))) {
            localServer.gateCancelled = true;
            return;
          }
          await route.fulfill({ json: { ready: true } });
        },
      },
    ]);
    await page.goto(localServer.origin);
    await page.evaluate(() => {
      void fetch('/api/v1/isolation/unreleased').catch(() => undefined);
    });
    await expect.poll(() => entered).toBe(true);
    expect(localServer.gateCancelled).toBe(false);
  });

  test('the next test sees its predecessor gate cancelled', async ({ page, localServer }) => {
    expect(localServer.delayedCompleted).toBe(true);
    expect(localServer.gateCancelled).toBe(true);
    await page.goto(localServer.origin);
    await expect(page.getByRole('heading')).toHaveText('API isolation');
  });
});

function listen(server: Server): Promise<void> {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });
}

test('an unexpected API call retains its explicit 501 response', async ({ page, localServer }) => {
  await page.goto(localServer.origin);
  const response = await page.evaluate(async () => {
    const result = await fetch('/api/v1/unexpected-fixture-request', { method: 'POST' });
    return { status: result.status, body: await result.json() };
  });
  expect(response).toEqual({
    status: 501,
    body: {
      error: 'unmocked_api_call',
      method: 'POST',
      url: `${localServer.origin}/api/v1/unexpected-fixture-request`,
    },
  });
});

test('the transport boundary rejects API reads and native pagehide sends outside page routes', async ({
  page,
  localServer,
  apiNetworkGuard,
}) => {
  await page.goto(localServer.origin);
  // Model the interception lost when a target is deleted, while observing real
  // browser sends and the transport response directly on the live target.
  await page.unrouteAll({ behavior: 'wait' });
  const response = await page.evaluate(async () => {
    const result = await fetch('/api/v1/isolation/transport-boundary');
    return { status: result.status, body: await result.json() };
  });
  expect(response).toEqual({
    status: 501,
    body: {
      error: 'unmocked_api_call',
      method: 'GET',
      url: `${localServer.origin}/api/v1/isolation/transport-boundary`,
    },
  });
  await page.evaluate(() => {
    window.addEventListener('pagehide', () => {
      navigator.sendBeacon('/api/v1/avatars/sessions/release?fixture_iteration=transport', '{}');
      void fetch('/api/v1/avatars/sessions/failure?fixture_iteration=transport', {
        method: 'POST',
        body: '{}',
        keepalive: true,
      }).catch(() => undefined);
    });
  });
  await page.goto(`${localServer.origin}/after-pagehide`);
  await expect
    .poll(() =>
      apiNetworkGuard.blockedRequests.filter(request => request.includes('/sessions/')).sort()
    )
    .toEqual([
      `POST ${localServer.origin}/api/v1/avatars/sessions/failure?fixture_iteration=transport`,
      `POST ${localServer.origin}/api/v1/avatars/sessions/release?fixture_iteration=transport`,
    ]);
  expect(localServer.escaped).toEqual([]);
});

test('opaque CONNECT and unmocked WebSocket upgrades never reach the server', async ({
  localServer,
  apiNetworkGuard,
}) => {
  const proxy = new URL(apiNetworkGuard.proxy.server);
  const target = new URL(localServer.origin).host;
  for (const request of [
    `CONNECT ${target} HTTP/1.1\r\nHost: ${target}\r\n\r\n`,
    `GET ${localServer.origin}/api/v1/isolation/socket HTTP/1.1\r\nHost: ${target}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n`,
  ]) {
    const response = await new Promise<string>((resolve, reject) => {
      const socket = connect(Number(proxy.port), proxy.hostname, () => socket.write(request));
      const chunks: Buffer[] = [];
      socket.on('data', chunk => chunks.push(chunk));
      socket.once('error', reject);
      socket.once('end', () => resolve(Buffer.concat(chunks).toString()));
    });
    expect(response).toMatch(/^HTTP\/1\.1 501 Unmocked transport\r\n/);
  }
  // Chromium may also probe its configured proxy with its own denied CONNECT.
  // These assertions observe exactly the two requests sent to this test server.
  expect(apiNetworkGuard.blockedRequests.filter(request => request.includes(target))).toEqual([
    `CONNECT ${target}`,
    `UPGRADE ${localServer.origin}/api/v1/isolation/socket`,
  ]);
  expect(localServer.escaped).toEqual([]);
});

test.describe.serial('a cancelled upstream response stays in its owning test', () => {
  test('quarantine ends an unfinished HTTP body without a worker error', async ({
    page,
    localServer,
    apiNetworkGuard,
  }) => {
    await page.goto(localServer.origin);
    const status = await page.evaluate(async () => {
      const response = await fetch('/isolation-stream');
      void response.text().catch(() => {
        document.title = 'Upstream body cancelled';
      });
      return response.status;
    });
    expect(status).toBe(200);
    apiNetworkGuard.quarantine();
    await expect(page).toHaveTitle('Upstream body cancelled');
    expect(localServer.escaped).toEqual([]);
  });

  test('the following context can read its document normally', async ({ page, localServer }) => {
    await page.goto(localServer.origin);
    await expect(page.getByRole('heading')).toHaveText('API isolation');
    expect(localServer.escaped).toEqual([]);
  });
});

for (const iteration of [1, 2, 3, 4, 5]) {
  test(`pending reads, SSE and unload notifications remain isolated (${iteration})`, async ({
    page,
    localServer,
    mockApi,
  }) => {
    const pending: string[] = [];
    await mockApi([
      {
        ...idleNotificationStream,
        handler: route => {
          pending.push(new URL(route.request().url()).pathname);
        },
      },
      {
        url: '**/api/v1/isolation/pending/*',
        method: 'GET',
        handler: route => {
          pending.push(new URL(route.request().url()).pathname);
        },
      },
      {
        url: '**/api/v1/avatars/sessions/release?fixture_iteration=*',
        method: 'POST',
        status: 204,
      },
      {
        url: '**/api/v1/avatars/sessions/failure?fixture_iteration=*',
        method: 'POST',
        status: 204,
      },
    ]);
    await page.goto(localServer.origin);
    await page.evaluate(fixtureIteration => {
      new EventSource('/api/v1/notifications/stream');
      for (const name of ['config', 'health', 'messages']) {
        void fetch(`/api/v1/isolation/pending/${name}`).catch(() => undefined);
      }
      window.addEventListener('pagehide', () => {
        navigator.sendBeacon(
          `/api/v1/avatars/sessions/release?fixture_iteration=${fixtureIteration}`,
          '{}'
        );
        void fetch(`/api/v1/avatars/sessions/failure?fixture_iteration=${fixtureIteration}`, {
          method: 'POST',
          body: '{}',
          keepalive: true,
        }).catch(() => undefined);
      });
    }, iteration);
    await expect
      .poll(() => pending.slice().sort())
      .toEqual([
        '/api/v1/isolation/pending/config',
        '/api/v1/isolation/pending/health',
        '/api/v1/isolation/pending/messages',
        '/api/v1/notifications/stream',
      ]);
    // The fixture teardown closes this live document with its requests pending.
    expect(localServer.escaped).toEqual([]);
  });
}

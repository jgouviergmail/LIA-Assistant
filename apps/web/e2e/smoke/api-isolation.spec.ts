/** The API boundary must remain hermetic while the browser closes its page. */
import { createServer, type Server } from 'node:http';
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
        response.writeHead(200, { 'Content-Type': 'text/html' }).end('<h1>API isolation</h1>');
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
      { url: '**/api/v1/avatars/sessions/release', method: 'POST', status: 204 },
      { url: '**/api/v1/avatars/sessions/failure', method: 'POST', status: 204 },
    ]);
    await page.goto(localServer.origin);
    await page.evaluate(() => {
      new EventSource('/api/v1/notifications/stream');
      for (const name of ['config', 'health', 'messages']) {
        void fetch(`/api/v1/isolation/pending/${name}`).catch(() => undefined);
      }
      window.addEventListener('pagehide', () => {
        navigator.sendBeacon('/api/v1/avatars/sessions/release', '{}');
        void fetch('/api/v1/avatars/sessions/failure', {
          method: 'POST',
          body: '{}',
          keepalive: true,
        }).catch(() => undefined);
      });
    });
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

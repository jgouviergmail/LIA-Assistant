/** A Playwright CLI program, not a test spec. Data never comes from a real API. */
import type { Page } from '@playwright/test';
import {
  CAPTURE_TIME,
  debugHistory,
  messages,
  publicScreenshotRoutes,
} from './public-screenshot-data';

interface CaptureInput {
  baseUrl: string;
  outputDir: string;
  time: string;
  routes: { url: string; json: unknown; status?: number }[];
  debug: typeof debugHistory;
  game: string;
  gameMessages: ReturnType<typeof messages>;
}

async function capture(page: Page, input: CaptureInput) {
  const unexpected: string[] = [];
  const errors: string[] = [];
  const origin = new URL(input.baseUrl).origin;
  page.on('pageerror', error => errors.push(error.stack ?? error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    // The app's public Material Symbols font has no account data or credentials.
    if (['https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(url.origin)) {
      await route.continue();
      return;
    }
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpected.push(`${request.method()} ${url.origin === origin ? url.pathname : url.origin}`);
      await route.abort();
    } else await route.continue();
  });
  for (const fixture of input.routes) {
    await page.route(fixture.url, route =>
      route.fulfill({ status: fixture.status ?? 200, json: fixture.json })
    );
  }
  await page.route('**/api/v1/notifications/stream', () => undefined);
  await page.routeWebSocket('**/*', socket => socket.close());
  await page.routeWebSocket('**/api/v1/voice/ws/audio?ticket=*', socket => {
    socket.onMessage(message => {
      if (message === 'PING') socket.send(JSON.stringify({ type: 'pong' }));
    });
  });
  await page.context().addCookies([
    {
      name: 'lia_session',
      value: 'public-demo-session',
      domain: new URL(input.baseUrl).hostname,
      path: '/',
    },
  ]);
  await page.addInitScript(
    ({ debug, time }) => {
      // Init scripts also run in the skill's opaque sandbox; leave that frame alone.
      if (window !== window.top) return;
      // Playwright's serviceWorkers:block script throws inside opaque srcdoc frames.
      // Disable registration only in the app instead; no worker may bypass our mocks.
      navigator.serviceWorker.register = async () => {
        throw new DOMException('Disabled for public captures', 'NotAllowedError');
      };
      const now = new Date(time).getTime();
      Object.defineProperty(window, 'Date', {
        value: new Proxy(Date, {
          construct(target, args) {
            return Reflect.construct(target, args.length ? args : [now]);
          },
          get(target, key, receiver) {
            return key === 'now' ? () => now : Reflect.get(target, key, receiver);
          },
        }),
      });
      localStorage.setItem('theme', 'light');
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: { visible: true, style: 'smiley', size: 'sm', position: null },
          version: 0,
        })
      );
      sessionStorage.setItem('lia_debug_metrics_history', JSON.stringify(debug));
    },
    { debug: input.debug, time: input.time }
  );

  const report: { name: string; path: string; emails: string[] }[] = [];
  const assertMessageOrder = async (question: string, answer: string) => {
    const user = await page.getByText(question, { exact: true }).boundingBox();
    const assistant = await page.getByText(answer, { exact: true }).boundingBox();
    if (!user || !assistant || user.y + user.height > assistant.y)
      throw new Error('The user message must precede the assistant reply.');
  };
  const ready = async (path: string, text: string) => {
    await page.goto(`${input.baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
    await page.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(
      () =>
        getComputedStyle(document.body).fontFamily.includes('sans') &&
        document.querySelector('main')
    );
  };
  const save = async (name: string, fullPage = false) => {
    const viewport = page.viewportSize();
    if (fullPage && viewport) {
      // Full-page capture otherwise paints fixed backdrops only to the old
      // viewport boundary, leaving a visible seam below it. Render the whole
      // document inside the viewport before Chromium takes the screenshot.
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      if (height > 16000) throw new Error(`Unexpected document height in ${name}`);
      await page.setViewportSize({ width: viewport.width, height });
    }
    await page.mouse.move(0, 0);
    await page.waitForTimeout(400);
    // Data readiness does not imply that Next's optimized images have decoded.
    // In particular, a fresh production build may still be resizing the hero.
    await page.evaluate(() => {
      // Load lazy images too, including footer logos just outside the viewport.
      for (const image of document.images) image.loading = 'eager';
    });
    try {
      await page.waitForFunction(() =>
        [...document.images]
          .filter(image => image.getBoundingClientRect().height > 0)
          .every(image => image.complete && image.naturalWidth > 0)
      );
    } catch {
      const missing = await page.evaluate(() =>
        [...document.images]
          .filter(
            image =>
              image.getBoundingClientRect().height > 0 && (!image.complete || !image.naturalWidth)
          )
          .map(image => ({ alt: image.alt, src: image.currentSrc, complete: image.complete }))
      );
      throw new Error(JSON.stringify({ name, missing, errors, unexpected }));
    }
    await page.evaluate(async () => {
      await Promise.all(
        [...document.images]
          .filter(image => image.getBoundingClientRect().height > 0)
          .map(image => image.decode())
      );
    });
    const text = await page.locator('body').innerText();
    if (
      /Something went wrong|Error in (?:chat|dashboard)|Could not generate|Failed to load|\bNaN\b/.test(
        text
      )
    )
      throw new Error(`Broken capture: ${name}`);
    const emails = text.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g) ?? [];
    if (emails.some(email => !/@example\.(test|com|org|net)$/.test(email)))
      throw new Error(`Non-demo email in ${name}`);
    if (/\bsk-[\w-]{16,}|\bAIza[\w-]{20,}/.test(text))
      throw new Error(`Credential-like text in ${name}`);
    if (/\b(?:settings|capabilities)\.[\w.]+/.test(text))
      throw new Error(`Untranslated fixture label in ${name}`);
    if (unexpected.length || errors.length)
      throw new Error(JSON.stringify({ name, unexpected, errors }));
    const path = `${input.outputDir}/${name}.png`;
    await page.screenshot({ path, fullPage, animations: 'disabled', caret: 'hide' });
    report.push({ name, path, emails });
    if (fullPage && viewport) await page.setViewportSize(viewport);
  };

  await ready('/en/dashboard', 'Design review');
  await save('homepage', true);
  await save('dashboard-wide');
  await page.setViewportSize({ width: 390, height: 844 });
  await save('dashboard-narrow', true);
  await page.setViewportSize({ width: 1440, height: 1100 });

  await ready('/en/dashboard/chat', 'Design review');
  await assertMessageOrder(
    'Help me prepare my day and show my next two appointments.',
    'You have a clear plan for today: a design review this morning, then a short project check-in after lunch.'
  );
  await save('chat');
  await page.route('**/api/v1/system-settings/debug-panel-status', route =>
    route.fulfill({ json: { enabled: true, user_access_available: true } })
  );
  await ready('/en/dashboard/chat', 'Design review');
  await assertMessageOrder(
    'Help me prepare my day and show my next two appointments.',
    'You have a clear plan for today: a design review this morning, then a short project check-in after lunch.'
  );
  const separator = page.getByRole('separator', { name: 'Resize the debug panel' });
  await separator.waitFor({ state: 'visible' });
  await save('chat-debug-panel');

  await page.route('**/api/v1/system-settings/debug-panel-status', route =>
    route.fulfill({ json: { enabled: false, user_access_available: true } })
  );

  await page.route('**/api/v1/conversations/me/messages*', route =>
    route.fulfill({ json: input.gameMessages })
  );
  await ready('/en/dashboard/chat', 'Tic-Tac-Toe');
  const game = page.frameLocator('iframe.lia-skill-app-widget__iframe');
  await game.getByRole('button').first().waitFor({ state: 'visible' });
  await assertMessageOrder(
    'Let’s play a game of Tic-Tac-Toe.',
    'Here is an interactive game. Click a cell to play.'
  );
  await save('chat-interactive-skills');

  await ready('/en/dashboard/settings', 'Settings');
  await save('settings-preferences');
  const rail = page.getByRole('navigation', { name: 'Settings sections' });
  await rail.getByRole('button', { name: 'LIA Style', exact: true }).scrollIntoViewIfNeeded();
  await page
    .getByRole('heading', { name: 'Identity & Memory', exact: true })
    .evaluate(element => element.scrollIntoView({ block: 'start' }));
  await page.evaluate(() => window.scrollBy(0, -88));
  await save('settings-features');
  await rail
    .getByRole('button', { name: 'User Administration', exact: true })
    .scrollIntoViewIfNeeded();
  await page
    .getByRole('heading', { name: 'Users & Access', exact: true })
    .evaluate(element => element.scrollIntoView({ block: 'start' }));
  await page.evaluate(() => window.scrollBy(0, -88));
  await save('settings-administration');

  await ready('/en/dashboard/settings?section=memories', 'Long-term Memory');
  await rail
    .getByRole('button', { name: 'Long-term Memory', exact: true })
    .scrollIntoViewIfNeeded();
  const preferences = page.getByRole('button', { name: /Preferences \(/ });
  if (await preferences.count()) await preferences.first().click();
  await page.getByText('I prefer concise answers', { exact: false }).waitFor({ state: 'visible' });
  await save('settings-features-memory');

  await ready('/en/dashboard/settings?section=psyche', 'Psyche Engine');
  await rail.getByRole('button', { name: 'Psyche Engine', exact: true }).scrollIntoViewIfNeeded();
  await page
    .getByRole('button', { name: /Psyche State/ })
    .first()
    .click();
  await page.getByText('LIA is calm, curious', { exact: false }).waitFor({ state: 'visible' });
  await save('settings-features-psyche');

  await ready('/en/dashboard/settings?section=admin-capabilities', 'Capabilities');
  await rail
    .getByRole('button', { name: 'Platform capabilities', exact: true })
    .scrollIntoViewIfNeeded();
  await page.getByRole('switch').first().waitFor({ state: 'visible' });
  await save('settings-administration-oneclick');
  await ready('/en/dashboard/settings?section=admin-llm-config', 'LLM Configuration');
  await rail
    .getByRole('button', { name: 'LLM Configuration', exact: true })
    .scrollIntoViewIfNeeded();
  await page.getByText('gpt-4.1-mini', { exact: false }).first().waitFor({ state: 'visible' });
  await save('settings-administration-llm');
  await ready('/en/faq', 'Frequently');
  await save('faq');
  return { fixtureTime: input.time, captures: report, unexpected, errors };
}

export function createCaptureCode(baseUrl: string, outputDir: string, game: string): string {
  const routes = publicScreenshotRoutes().flatMap(route =>
    typeof route.url === 'string' && route.json !== undefined
      ? [{ url: route.url, json: route.json, status: route.status }]
      : []
  );
  const gameMessages = messages(
    '<p>Here is an interactive game. Click a cell to play.</p><div class="lia-skill-app" data-registry-id="demo-tic-tac-toe"></div>',
    {
      widgets: {
        'demo-tic-tac-toe': {
          id: 'demo-tic-tac-toe',
          type: 'SKILL_APP',
          payload: {
            skill_name: 'tic-tac-toe',
            title: 'Tic-Tac-Toe',
            html_content: game,
            aspect_ratio: 0.75,
            is_system_skill: true,
          },
          meta: { source: 'skill', timestamp: CAPTURE_TIME },
        },
      },
    },
    'Let’s play a game of Tic-Tac-Toe.'
  );
  return `async (page) => (${capture.toString()})(page, ${JSON.stringify({ baseUrl, outputDir, time: CAPTURE_TIME, routes, debug: debugHistory, game, gameMessages })})`;
}

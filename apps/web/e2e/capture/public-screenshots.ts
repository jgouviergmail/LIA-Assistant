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
  routes: { url: string | { regex: string }; json: unknown; status?: number }[];
  debug: typeof debugHistory;
  skillMessages: ReturnType<typeof messages>;
  fontCss: string;
  fontPath: string;
}

async function capture(page: Page, input: CaptureInput) {
  const unexpected: string[] = [];
  const errors: string[] = [];
  const origin = new URL(input.baseUrl).origin;
  page.on('pageerror', error => errors.push(error.stack ?? error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`${message.text()} (${message.location().url})`);
  });
  page.on('response', response => {
    if (response.status() >= 400)
      errors.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`);
  });
  await page.setViewportSize({ width: 1600, height: 1100 });
  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpected.push(`${request.method()} ${url.origin === origin ? url.pathname : url.origin}`);
      await route.abort();
    } else await route.continue();
  });
  for (const fixture of input.routes) {
    const url = typeof fixture.url === 'string' ? fixture.url : new RegExp(fixture.url.regex);
    await page.route(url, route =>
      route.fulfill(
        fixture.status === 204
          ? { status: 204, body: '' }
          : { status: fixture.status ?? 200, json: fixture.json }
      )
    );
  }
  await page.route('https://fonts.googleapis.com/**', route =>
    route.fulfill({
      contentType: 'text/css',
      body: input.fontCss,
      headers: { 'Access-Control-Allow-Origin': '*' },
    })
  );
  await page.route('https://fonts.gstatic.com/lia-e2e/MaterialSymbolsOutlined.woff2', route =>
    route.fulfill({
      contentType: 'font/woff2',
      path: input.fontPath,
      headers: { 'Access-Control-Allow-Origin': '*' },
    })
  );
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
    { name: 'lia_gender', value: 'male', domain: new URL(input.baseUrl).hostname, path: '/' },
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
          state: {
            visible: true,
            style: 'bip',
            size: 'xl',
            position: { xPct: 1.2, yPct: 73 },
            landingPosition: { xPct: 1.2, yPct: 73 },
          },
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
  const showChatStart = async () => {
    await page.mouse.move(220, 450);
    await page.mouse.wheel(0, -4000);
    await page.waitForTimeout(500);
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
    await page.mouse.move(10, 90);
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
    const frame = page.viewportSize();
    if (frame) {
      const centre = [
        'homepage',
        'dashboard-wide',
        'chat',
        'chat-debug-panel',
        'settings-features-memory',
        'settings-features-psyche',
      ].includes(name);
      await page.mouse.move(
        frame.width * (centre ? 0.5 : 0.65),
        frame.height * (centre ? 0.5 : 0.3),
        { steps: 12 }
      );
      await page.waitForTimeout(160);
    }
    const widget = page.locator('.lia-eyes-widget .lia-eyes--xl');
    if (
      !['faq', 'dashboard-narrow'].includes(name) &&
      !(await widget.filter({ visible: true }).count())
    )
      throw new Error(`Maximum-size robot missing in ${name}`);
    await page.screenshot({ path, fullPage, animations: 'allow', caret: 'hide' });
    report.push({ name, path, emails });
    if (fullPage && viewport) await page.setViewportSize(viewport);
  };

  await ready('/en/dashboard', 'Design review');
  await save('homepage', true);
  await save('dashboard-wide');
  await page.setViewportSize({ width: 390, height: 844 });
  await save('dashboard-narrow');
  await page.setViewportSize({ width: 1600, height: 1100 });

  await page.setViewportSize({ width: 1600, height: 1400 });
  await ready('/en/dashboard/chat', 'Design review');
  if ((await page.locator('.lia-card.lia-event').count()) !== 2)
    throw new Error('Daily agenda must use two authentic EventCard renderings');
  await assertMessageOrder(
    'Help me prepare my day and show my next two appointments.',
    'You have a clear plan for today: a design review this morning, then a short project check-in after lunch.'
  );
  await showChatStart();
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
  await showChatStart();
  await save('chat-debug-panel');

  await page.route('**/api/v1/system-settings/debug-panel-status', route =>
    route.fulfill({ json: { enabled: false, user_access_available: true } })
  );

  await page.route('**/api/v1/conversations/me/messages*', route =>
    route.fulfill({ json: input.skillMessages })
  );
  await page.setViewportSize({ width: 1600, height: 1200 });
  await ready('/en/dashboard/chat', 'Shape your weekend, right here');
  const skill = page.frameLocator('iframe.lia-skill-app-widget__iframe');
  await skill.getByText('A weekend in Lyon', { exact: true }).waitFor({ state: 'visible' });
  await assertMessageOrder(
    'Create a visual budget studio for a weekend in Lyon: two travellers, two nights, and a budget I can adjust.',
    'Shape your weekend, right here'
  );
  const budget = skill.locator('#budget');
  if ((await budget.inputValue()) !== '760') throw new Error('Unexpected initial skill budget');
  for (let index = 0; index < 7; index++) await budget.press('ArrowRight');
  await skill.locator('#margin').getByText('€316', { exact: true }).waitFor({ state: 'visible' });
  await showChatStart();
  await save('chat-interactive-skills');

  await ready('/en/dashboard/settings', 'Settings');
  await save('settings-preferences');
  await page.route('**/api/v1/personalities', route =>
    route.fulfill({
      json: {
        personalities: [
          {
            id: 'demo-style-balanced',
            code: 'default',
            emoji: '⚖️',
            is_default: true,
            title: 'Balanced',
            description: 'Clear answers, a warm tone and practical next steps.',
          },
          {
            id: 'demo-style-teacher',
            code: 'teacher',
            emoji: '🧐',
            is_default: false,
            title: 'Patient teacher',
            description: 'Explain unfamiliar ideas step by step, with examples.',
          },
          {
            id: 'demo-style-creative',
            code: 'creative',
            emoji: '✨',
            is_default: false,
            title: 'Creative partner',
            description: 'Explore alternatives, connect ideas and test fresh directions.',
          },
          {
            id: 'demo-style-direct',
            code: 'direct',
            emoji: '🤝',
            is_default: false,
            title: 'Straight to the point',
            description: 'Keep it concise, concrete and focused on the decision.',
          },
        ],
        count: 4,
      },
    })
  );
  await ready('/en/dashboard/settings?section=personality', 'Balanced');
  const rail = page.getByRole('navigation', { name: 'Settings sections' });
  await page.locator('#settings-section-personality').waitFor({ state: 'visible' });
  await save('settings-features');
  await rail.getByRole('button', { name: 'User Administration', exact: true }).click();
  await page.locator('#settings-section-admin-users').waitFor({ state: 'visible' });
  await save('settings-administration');

  await ready('/en/dashboard/settings?section=memories', 'Long-term Memory');
  await rail
    .getByRole('button', { name: 'Long-term Memory', exact: true })
    .scrollIntoViewIfNeeded();
  const preferences = page.getByRole('button', { name: /Preferences \(/ });
  if (await preferences.count()) await preferences.first().click();
  await page.getByText('I prefer concise answers', { exact: false }).waitFor({ state: 'visible' });
  await save('settings-features-memory');

  await ready('/en/dashboard/settings?section=psyche', 'LIA’s psyche');
  await rail.getByRole('button', { name: 'LIA’s psyche', exact: true }).scrollIntoViewIfNeeded();
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

export function createCaptureCode(
  baseUrl: string,
  outputDir: string,
  skillFrame: { title: string; html: string; aspect_ratio: number },
  eventCards: string,
  fontCss: string,
  fontPath: string
): string {
  const routes = publicScreenshotRoutes(eventCards).flatMap(route =>
    route.json !== undefined
      ? [
          {
            url: typeof route.url === 'string' ? route.url : { regex: route.url.source },
            json: route.json,
            status: route.status,
          },
        ]
      : []
  );
  const skillMessages = messages(
    '<h2>Shape your weekend, right here</h2><p>A small Python skill prepares this interactive budget studio. Adjust the trip and watch the categories, total and remaining budget change together. These are example estimates; no booking prices were checked.</p><div class="lia-skill-app" data-registry-id="demo-weekend-budget"></div>',
    {
      widgets: {
        'demo-weekend-budget': {
          id: 'demo-weekend-budget',
          type: 'SKILL_APP',
          payload: {
            skill_name: 'weekend-budget-studio',
            title: skillFrame.title,
            html_content: skillFrame.html,
            aspect_ratio: skillFrame.aspect_ratio,
            is_system_skill: false,
          },
          meta: { source: 'skill', timestamp: CAPTURE_TIME },
        },
      },
    },
    'Create a visual budget studio for a weekend in Lyon: two travellers, two nights, and a budget I can adjust.'
  );
  return `async (page) => (${capture.toString()})(page, ${JSON.stringify({ baseUrl, outputDir, time: CAPTURE_TIME, routes, debug: debugHistory, skillMessages, fontCss, fontPath })})`;
}

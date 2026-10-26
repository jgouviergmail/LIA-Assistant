import { openNativeWorld } from '../fixtures/world-admission';
/** Real cookie/session/SQL/Redis journeys. No paid provider or transport mock. */
import { test, expect, type Browser, type BrowserContext, type Page } from './fixtures';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
import { worldTransportFault } from './transport';

function labels(lng: string) {
  const value: unknown = JSON.parse(
    readFileSync(join(__dirname, '../../locales', lng, 'translation.json'), 'utf8')
  );
  return (path: string): string => {
    let node = value;
    for (const key of path.split('.')) {
      node = node && typeof node === 'object' && key in node ? Reflect.get(node, key) : undefined;
    }
    if (typeof node !== 'string') throw new Error('Missing authored label: ' + path);
    return node;
  };
}
const controlTimelines = new WeakMap<Page, unknown[]>();
interface Visitor {
  context: BrowserContext;
  page: Page;
  t: ReturnType<typeof labels>;
}
async function signIn(context: BrowserContext, baseURL: string, index: number) {
  const result = await context.request.post('/api/v1/world-proof/session', {
    headers: { Origin: new URL(baseURL).origin },
    data: { index },
  });
  expect(result.status()).toBe(200);
}
async function enter(page: Page, lng: string, alias: string, baseURL: string) {
  const t = labels(lng);
  await installOfflineFonts(page);
  await openNativeWorld(page, alias, worldProofUrl(baseURL, lng));
  if (await page.locator('input[name="world-presence-consent"]').isVisible())
    await page.locator('input[name="world-presence-consent"]').check();
  const ticket = page.waitForResponse(response => response.url().endsWith('/world/ticket'));
  await page.getByRole('button', { name: t('world.session.enter'), exact: true }).click();
  expect((await ticket).status()).toBe(200);
  const chat = page.getByRole('button', { name: t('world.messages.action'), exact: true });
  const takeover = page.getByRole('button', { name: t('world.session.takeover'), exact: true });
  await expect(chat.or(takeover)).toBeVisible();
  if (await takeover.isVisible()) await takeover.click();
  await expect(chat).toBeEnabled();
  return t;
}
async function visitor(
  browser: Browser,
  baseURL: string,
  index: number,
  lng: string,
  alias: string,
  fault?: ReturnType<typeof worldTransportFault>
): Promise<Visitor> {
  const context = await browser.newContext({
    baseURL,
    serviceWorkers: 'block',
    viewport: { width: 1280, height: 800 },
  });
  try {
    await signIn(context, baseURL, index);
    const page = await context.newPage();
    const timeline: unknown[] = [];
    controlTimelines.set(page, timeline);
    page.on('websocket', socket => {
      if (!socket.url().endsWith('/world/ws')) return;
      let last = '';
      socket.on('framereceived', ({ payload }) => {
        const frame = JSON.parse(String(payload)) as {
          type: string;
          status?: string;
          controlling?: boolean;
          you?: { alias: string } | null;
        };
        if (frame.type !== 'snapshot') return;
        const state = JSON.stringify({
          status: frame.status,
          controlling: frame.controlling,
          alias: frame.you?.alias ?? null,
        });
        if (state !== last) {
          timeline.push({ at: Date.now(), state: JSON.parse(state) });
          last = state;
        }
      });
    });
    await fault?.install(page);
    const t = await enter(page, lng, alias, baseURL);
    return { context, page, t };
  } catch (error) {
    await context.close();
    throw error;
  }
}
async function openChat(person: Visitor, alias: string) {
  await person.page.bringToFront();
  try {
    await person.page
      .getByRole('button', { name: person.t('world.messages.action'), exact: true })
      .click();
  } catch (error) {
    await test.info().attach('world-control-timeline', {
      body: JSON.stringify(controlTimelines.get(person.page) ?? []),
      contentType: 'application/json',
    });
    throw error;
  }
  await person.page
    .getByRole('navigation', { name: person.t('world.messages.conversations'), exact: true })
    .getByRole('button')
    .filter({ hasText: alias })
    .filter({ has: person.page.getByText(person.t('world.messages.present'), { exact: true }) })
    .click();
  await expect(person.page.getByRole('log')).toBeVisible();
}
async function compose(person: Visitor, alias: string, text: string) {
  await person.page.bringToFront();
  const directory = person.page.getByRole('navigation', {
    name: person.t('world.messages.conversations'),
    exact: true,
  });
  if (await directory.isVisible())
    await directory
      .getByRole('button')
      .filter({ hasText: alias })
      .filter({ has: person.page.getByText(person.t('world.messages.present'), { exact: true }) })
      .click();
  await expect(
    person.page.getByRole('form', {
      name: person.t('world.messages.to').replace('{{name}}', alias),
      exact: true,
    })
  ).toBeVisible();
  await person.page.getByRole('textbox', { name: person.t('world.messages.message') }).fill(text);
  await person.page.getByRole('checkbox', { name: person.t('world.messages.consent') }).check();
}
async function send(person: Visitor, alias: string, text: string) {
  await compose(person, alias, text);
  const response = person.page.waitForResponse(value =>
    value.url().endsWith('/world/messages/send')
  );
  await person.page
    .getByRole('button', { name: person.t('world.messages.send'), exact: true })
    .click();
  const result = await response;
  expect(result.status()).toBe(202);
  const body: unknown = await result.json();
  if (!body || typeof body !== 'object' || !('id' in body) || typeof body.id !== 'string')
    throw new Error('Missing owned acknowledgment');
  await expect(
    person.page.getByRole('textbox', { name: person.t('world.messages.message') })
  ).toHaveValue('');
  return body.id;
}
async function close(people: Visitor[]) {
  try {
    for (const person of people) {
      if (!person.page.isClosed()) {
        await person.page.bringToFront();
        // Focus re-verifies the account and temporarily hides its portal.
        // Click the owned close action after it reappears; an immediate Escape
        // can hit the hidden interval and leave the dialog covering Leave.
        const closeDialog = person.page.locator('[data-world-messages]').getByRole('button', {
          name: person.t('common.close'),
          exact: true,
        });
        if (await closeDialog.count()) await closeDialog.click();
        const leave = person.page.getByRole('button', {
          name: person.t('world.session.leave'),
          exact: true,
        });
        if (await leave.count()) await leave.last().click();
      }
    }
  } finally {
    for (const context of new Set(people.map(person => person.context))) await context.close();
  }
}

test('a real bilingual conversation works in both directions and a failed translation remains recoverable', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Isolated native preview required');
  const people: Visitor[] = [];
  const recipientBrowser = await browser.browserType().launch({ headless: true });
  try {
    const a = await visitor(browser, baseURL, 3, 'de', 'Conversation-A');
    people.push(a);
    const b = await visitor(recipientBrowser, baseURL, 4, 'es', 'Conversation-B');
    people.push(b);
    await openChat(a, 'Conversation-B');
    await openChat(b, 'Conversation-A');
    const first = await send(a, 'Conversation-B', 'Hallo, schön, dich kennenzulernen.');
    await b.page.bringToFront();
    await expect(
      b.page
        .locator(`[data-world-message="${first}"]`)
        .getByText('Hola, encantado de conocerte.', { exact: true })
    ).toBeVisible();
    const reply = await send(b, 'Conversation-A', 'Hola, encantado de conocerte.');
    await a.page.bringToFront();
    await expect(
      a.page
        .locator(`[data-world-message="${reply}"]`)
        .getByText('Hallo, schön, dich kennenzulernen.', { exact: true })
    ).toBeVisible();
    const arbitrary = await send(a, 'Conversation-B', 'Rendez-vous dans le jardin à 15 h ?');
    await b.page.bringToFront();
    const failed = b.page.locator(`[data-world-message="${arbitrary}"]`);
    await expect(failed.getByText(b.t('world.messages.failed'), { exact: true })).toBeVisible();
    await expect(failed).not.toContainText('Rendez-vous');
    await failed.getByRole('button', { name: b.t('world.messages.show_original') }).click();
    await expect(
      failed.getByText('Rendez-vous dans le jardin à 15 h ?', { exact: true })
    ).toBeVisible();
  } finally {
    try {
      await close(people);
    } finally {
      await recipientBrowser.close();
    }
  }
});

test('a recipient recovers an interrupted mailbox read without losing a draft or resending', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Isolated native preview required');
  const people: Visitor[] = [];
  const recipientBrowser = await browser.browserType().launch({ headless: true });
  try {
    const a = await visitor(browser, baseURL, 2, 'en', 'Resume-A');
    people.push(a);
    const b = await visitor(recipientBrowser, baseURL, 8, 'en', 'Resume-B');
    people.push(b);
    await openChat(a, 'Resume-B');
    await openChat(b, 'Resume-A');
    const draft = b.page.getByRole('textbox', { name: b.t('world.messages.message') });
    await draft.fill('My retained draft');
    await b.context.route('**/world/messages/read', route => route.abort('failed'));
    await expect(b.page.getByRole('dialog').getByRole('status')).toContainText(
      b.t('world.messages.offline')
    );
    let sends = 0;
    a.page.on('request', request => {
      if (request.url().endsWith('/world/messages/send')) sends++;
    });
    const id = await send(a, 'Resume-B', 'A real message during the read interruption.');
    await expect(b.page.locator(`[data-world-message="${id}"]`)).toHaveCount(0);
    await b.page.bringToFront();
    const retry = b.page.getByRole('button', { name: b.t('common.retry'), exact: true });
    await expect(retry).toBeVisible();
    // Keep the failure installed through the foreground revalidation and one
    // explicit retry. Removing it earlier races the automatic visibility read.
    const failedRetry = b.page.waitForRequest(request =>
      request.url().endsWith('/world/messages/read')
    );
    await retry.click();
    await failedRetry;
    await expect(b.page.getByRole('dialog').getByRole('status')).toContainText(
      b.t('world.messages.offline')
    );
    await b.context.unroute('**/world/messages/read');
    await retry.click();
    await expect(b.page.locator(`[data-world-message="${id}"]`)).toHaveCount(1);
    await expect(draft).toHaveValue('My retained draft');
    expect(sends).toBe(1);
    const reply = await send(b, 'Resume-A', 'Recovered and received.');
    await a.page.bringToFront();
    await expect(a.page.locator(`[data-world-message="${reply}"]`)).toContainText(
      'Recovered and received.'
    );
  } finally {
    try {
      await close(people);
    } finally {
      await recipientBrowser.close();
    }
  }
});

test('an account change in another tab withdraws the previous private conversation before further interaction', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Isolated native preview required');
  const people: Visitor[] = [];
  const recipientBrowser = await browser.browserType().launch({ headless: true });
  try {
    const a = await visitor(browser, baseURL, 1, 'fr', 'Original-tab');
    people.push(a);
    const b = await visitor(recipientBrowser, baseURL, 2, 'fr', 'Draft-peer');
    people.push(b);
    await openChat(a, 'Draft-peer');
    await a.page
      .getByRole('textbox', { name: a.t('world.messages.message') })
      .fill('PRIVATE-OLD-ACCOUNT-DRAFT');
    const other = await a.context.newPage();
    people.push({ context: a.context, page: other, t: labels('de') });
    await other.bringToFront();
    await signIn(a.context, baseURL, 3);
    await enter(other, 'de', 'Other-account', baseURL);
    await a.page.bringToFront();
    await expect(a.page.getByRole('log')).not.toBeVisible();
    await expect(
      a.page.getByRole('textbox', { name: a.t('world.messages.message') })
    ).not.toBeVisible();
    await a.page
      .getByRole('button', { name: a.t('world.session.reload_account'), exact: true })
      .click();
    // A reload keeps this tab's route or adopts the shared locale cookie.
    // Privacy must hold in either supported locale used by these two tabs.
    const loadedLanguage = await a.page.locator('html').getAttribute('lang');
    if (loadedLanguage !== 'fr' && loadedLanguage !== 'de')
      throw new Error('Unexpected reloaded conversation locale');
    await expect(a.page.locator('[data-world-public-name]')).toBeVisible();
    await expect(a.page.getByRole('log')).not.toBeVisible();
  } finally {
    try {
      await close(people);
    } finally {
      await recipientBrowser.close();
    }
  }
});

test('free text, reciprocal replies, reload and a lost acknowledgment work without duplicate delivery', async ({
  browser,
  baseURL,
}, info) => {
  if (!baseURL) throw new Error('Isolated native preview required');
  const people: Visitor[] = [];
  const recipientBrowser = await browser.browserType().launch({ headless: true });
  try {
    const transport = worldTransportFault();
    const a = await visitor(browser, baseURL, 1, 'fr', 'Libre-A', transport);
    people.push(a);
    const b = await visitor(recipientBrowser, baseURL, 7, 'fr', 'Libre-B');
    people.push(b);
    await openChat(a, 'Libre-B');
    const text =
      'Salut 👋\nOn explore le jardin ensemble ?\n' +
      Array.from(
        { length: 8 },
        (_, index) => 'Étape ' + (index + 1) + ' : retrouver la fontaine et le jardin.'
      ).join('\n');
    const first = await send(a, 'Libre-B', text);
    await b.page.bringToFront();
    await expect(
      b.page.getByRole('button', { name: b.t('world.messages.action'), exact: true })
    ).toHaveAccessibleDescription(/[1-9]/);
    await openChat(b, 'Libre-A');
    await expect(b.page.locator(`[data-world-message="${first}"]`)).toContainText(text);
    const reply = await send(b, 'Libre-A', 'Oui, allons-y ! 🌿');
    await a.page.bringToFront();
    await expect(a.page.locator(`[data-world-message="${reply}"]`)).toContainText(
      'Oui, allons-y ! 🌿'
    );
    let delivered = '';
    let sends = 0;
    await a.context.route('**/world/messages/send', async route => {
      sends++;
      const response = await route.fetch();
      expect(response.status()).toBe(202);
      const body: unknown = await response.json();
      if (!body || typeof body !== 'object' || !('id' in body) || typeof body.id !== 'string')
        throw new Error('Missing owned acknowledgment');
      delivered = body.id;
      await transport.disconnect();
      await route.abort('failed');
    });
    await compose(a, 'Libre-B', 'Le message est arrivé même si son accusé a été perdu.');
    await a.page.getByRole('button', { name: a.t('world.messages.send'), exact: true }).click();
    await expect(a.page.getByRole('textbox', { name: a.t('world.messages.message') })).toHaveValue(
      ''
    );
    expect(sends).toBe(1);
    expect(transport.connections()).toBeGreaterThanOrEqual(2);
    await b.page.bringToFront();
    await expect(b.page.locator(`[data-world-message="${delivered}"]`)).toHaveCount(1);
    await b.page.keyboard.press('Escape');
    await b.page.reload();
    await expect(b.page.locator('[data-world-public-name]')).toBeVisible();
    if (await b.page.locator('input[name="world-presence-consent"]').isVisible())
      await b.page.locator('input[name="world-presence-consent"]').check();
    await b.page.getByRole('button', { name: b.t('world.session.enter'), exact: true }).click();
    const takeover = b.page.getByRole('button', {
      name: b.t('world.session.takeover'),
      exact: true,
    });
    const chat = b.page.getByRole('button', { name: b.t('world.messages.action'), exact: true });
    await expect(takeover.or(chat)).toBeVisible();
    if (await takeover.isVisible()) await takeover.click();
    await expect(
      b.page.getByRole('button', { name: b.t('world.messages.action'), exact: true })
    ).toBeEnabled();
    await openChat(b, 'Libre-A');
    await expect(b.page.locator(`[data-world-message="${delivered}"]`)).toHaveCount(1);
    await expect(b.page.locator(`[data-world-message="${first}"]`)).toContainText(text);
    await a.context.unroute('**/world/messages/send');
    await b.page.setViewportSize({ width: 390, height: 660 });
    const log = b.page.getByRole('log');
    await expect
      .poll(() => log.evaluate(node => node.scrollHeight - node.clientHeight))
      .toBeGreaterThan(60);
    await log.hover();
    await b.page.mouse.wheel(0, -2000);
    const latest = b.page.getByRole('button', { name: b.t('world.messages.latest'), exact: true });
    await expect(latest).toBeVisible();
    // Browser wheel normalization can stop mid-history; preserve the position
    // actually reached, rather than assuming every engine scrolls to zero.
    let readingPosition = -1;
    await expect
      .poll(async () => {
        const position = await log.evaluate(node => node.scrollTop);
        const settled = Math.abs(position - readingPosition) < 0.01;
        readingPosition = position;
        return settled;
      })
      .toBe(true);
    const verified = b.page.waitForResponse(response => response.url().endsWith('/auth/me'));
    await b.page.evaluate(() => window.dispatchEvent(new Event('focus')));
    expect((await verified).status()).toBe(200);
    await expect(log).toBeVisible();
    // Browsers quantize programmatic scrollTop to a CSS pixel (measured in all
    // three engines); wheel positions can still be fractional in Firefox.
    await expect
      .poll(async () => Math.abs((await log.evaluate(node => node.scrollTop)) - readingPosition))
      .toBeLessThan(1);
    const arrival = await send(
      a,
      'Libre-B',
      'Un nouveau message pendant la lecture des précédents.'
    );
    await expect(b.page.locator(`[data-world-message="${arrival}"]`)).toHaveCount(1);
    // Browsers quantize programmatic scrollTop to a CSS pixel (measured in all
    // three engines); wheel positions can still be fractional in Firefox.
    await expect
      .poll(async () => Math.abs((await log.evaluate(node => node.scrollTop)) - readingPosition))
      .toBeLessThan(1);
    await latest.click();
    await expect(log).toBeFocused();
    await expect(b.page.locator(`[data-world-message="${arrival}"]`)).toBeInViewport();
    await b.page.setViewportSize({ width: 390, height: 844 });
    await expect(
      b.page.getByRole('button', { name: b.t('world.messages.send'), exact: true })
    ).toBeInViewport();
    await b.page.screenshot({ path: info.outputPath('conversation-mobile.png') });
    expect(sends).toBe(1);
  } finally {
    try {
      await close(people);
    } finally {
      await recipientBrowser.close();
    }
  }
});

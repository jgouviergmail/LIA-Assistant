import { createWorldDevice, closeWorldDevices, type WorldDevice } from '../fixtures/world-device';
import { openNativeWorld } from '../fixtures/world-admission';
/** Native cookies, BFF, SQL attempts and private Redis; translation is explicitly inert. */
import { test, expect, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function labels(lng: string): (key: string) => string {
  const locale: unknown = JSON.parse(
    readFileSync(join(__dirname, '../../locales', lng, 'translation.json'), 'utf8')
  );
  return key => {
    let value = locale;
    for (const segment of key.split('.')) value = record(value) ? value[segment] : undefined;
    if (typeof value !== 'string') throw new Error('Missing authored label: ' + key);
    return value;
  };
}
interface Visitor {
  context: BrowserContext;
  page: Page;
  t(key: string): string;
}

test('direct text stays private, translates before display, handles failure without resend and remains usable on phone', async ({
  browser,
  baseURL,
}, info) => {
  if (
    !baseURL ||
    ![
      '127.0.0.1',
      '127.0.0.4',
      'lia-world-social-candidate',
      '127.0.0.5',
      'lia-world-polish-candidate',
      'lia-world-final-candidate',
      'lia-world-qualification-web',
      '127.0.0.6',
      '127.0.0.7',
      '127.0.0.8',
    ].includes(new URL(baseURL).hostname)
  )
    throw new Error('Independent social proof host required');
  const origin = new URL(baseURL).origin;
  const visitors: Visitor[] = [];
  const devices: WorldDevice[] = [];
  const failures: string[] = [];
  const escaped: string[] = [];
  let sends = 0;
  try {
    for (const [index, lng, alias] of [
      [1, 'fr', 'Camille'],
      [2, 'en', 'Robin'],
      [3, 'de', 'Alex'],
    ] as const) {
      const device = await createWorldDevice(browser, {
        baseURL,
        viewport: { width: 1280, height: 800 },
        serviceWorkers: 'block',
      });
      devices.push(device);
      const context = device.context;
      const page = await context.newPage();
      await page.bringToFront();
      const t = labels(lng);
      visitors.push({ context, page, t });
      await installOfflineFonts(page);
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin === origin) return route.continue();
        escaped.push(url.origin);
        return route.abort();
      });
      page.on('pageerror', error => failures.push(error.name));
      page.on('request', request => {
        if (request.url().endsWith('/world/messages/send')) sends++;
      });
      page.on('websocket', socket => {
        if (!socket.url().endsWith('/world/ws')) return;
        socket.on('framereceived', event => {
          if (String(event.payload).includes('ravi de te rencontrer'))
            failures.push('private-text-in-public-snapshot');
        });
      });
      const session = await context.request.post('/api/v1/world-proof/session', {
        headers: { Origin: origin },
        data: { index },
      });
      expect(session.status()).toBe(200);
      const entry = worldProofUrl(baseURL, lng);
      await openNativeWorld(page, alias, entry);
      if (entry.pathname.endsWith('world-preview'))
        await expect(page.getByRole('note')).toContainText(t('world.session.proof_translation'));
      else expect((await context.request.get(`/${lng}/world-preview`)).status()).toBe(404);
      if (await page.locator('input[name="world-presence-consent"]').isVisible())
        await page.locator('input[name="world-presence-consent"]').check();
      await page.getByRole('button', { name: t('world.session.enter'), exact: true }).click();
      const chat = page.getByRole('button', { name: t('world.messages.action'), exact: true });
      const takeover = page.getByRole('button', { name: t('world.session.takeover'), exact: true });
      await expect(chat.or(takeover)).toBeVisible();
      if (await takeover.isVisible()) await takeover.click();
      await expect(chat).toBeEnabled();
    }
    const [sender, recipient, outsider] = visitors;
    for (const visitor of visitors) {
      await visitor.page.bringToFront();
      await visitor.page
        .getByRole('button', { name: visitor.t('world.messages.action'), exact: true })
        .click();
    }
    await sender.page.bringToFront();
    for (const [person, alias] of [
      [sender, 'Robin'],
      [recipient, 'Camille'],
      [outsider, 'Camille'],
    ] as const) {
      await person.page.bringToFront();
      await person.page
        .getByRole('navigation', { name: person.t('world.messages.conversations'), exact: true })
        .getByRole('button')
        .filter({ hasText: alias })
        .filter({ has: person.page.getByText(person.t('world.messages.present'), { exact: true }) })
        .click();
      await expect(person.page.getByRole('log')).toBeVisible();
    }
    await sender.page.bringToFront();
    await sender.page
      .getByRole('textbox', { name: sender.t('world.messages.message') })
      .fill('Bonjour, ravi de te rencontrer.');
    const send = sender.page.getByRole('button', {
      name: sender.t('world.messages.send'),
      exact: true,
    });
    await expect(send).toBeDisabled();
    await sender.page.getByRole('checkbox', { name: sender.t('world.messages.consent') }).check();
    await expect(send).toBeEnabled();
    const accepted = sender.page.waitForResponse(response =>
      response.url().endsWith('/world/messages/send')
    );
    await send.click();
    const acknowledgment: unknown = await (await accepted).json();
    if (!record(acknowledgment) || typeof acknowledgment.id !== 'string')
      throw new Error('Missing owned send acknowledgment');
    const article = recipient.page.locator(`[data-world-message="${acknowledgment.id}"]`);
    await recipient.page.bringToFront();
    await expect(article.getByText('Hello, pleased to meet you.', { exact: true })).toBeVisible();
    expect(await recipient.page.getByRole('log').textContent()).not.toContain('Bonjour, ravi');
    const bubble = recipient.page.locator('[data-world-speech="private"]');
    await expect(bubble).toContainText('Hello, pleased to meet you.');
    expect(await sender.page.locator('[data-world-speech="private"]').count()).toBe(0);
    expect(await outsider.page.locator('[data-world-speech="private"]').count()).toBe(0);
    await recipient.page.keyboard.press('Escape');
    await recipient.page.screenshot({ path: info.outputPath('recipient-private-bubble.png') });
    await recipient.page
      .getByRole('button', { name: recipient.t('world.messages.action'), exact: true })
      .click();

    expect(await outsider.page.getByRole('log').textContent()).not.toContain('pleased to meet');
    expect(
      await sender.page
        .getByRole('textbox', { name: sender.t('world.messages.message') })
        .inputValue()
    ).toBe('');
    await article
      .getByRole('button', { name: recipient.t('world.messages.show_original') })
      .click();
    await expect(
      article.getByText('Bonjour, ravi de te rencontrer.', { exact: true })
    ).toBeVisible();
    await sender.page.bringToFront();
    await sender.page
      .getByRole('textbox', { name: sender.t('world.messages.message') })
      .fill('<img src=x onerror=alert(1)>');
    const failedAcknowledgment = sender.page.waitForResponse(response =>
      response.url().endsWith('/world/messages/send')
    );
    await send.click();
    const failedResponse: unknown = await (await failedAcknowledgment).json();
    if (!record(failedResponse) || typeof failedResponse.id !== 'string')
      throw new Error('Missing owned failed-send acknowledgment');
    const failed = recipient.page.locator(`[data-world-message="${failedResponse.id}"]`);
    await recipient.page.bringToFront();
    await expect(
      failed.getByText(recipient.t('world.messages.failed'), { exact: true })
    ).toBeVisible();
    await failed.getByRole('button', { name: recipient.t('world.messages.show_original') }).click();
    await expect(failed.getByText('<img src=x onerror=alert(1)>', { exact: true })).toBeVisible();
    expect(await failed.locator('img').count()).toBe(0);
    expect(sends).toBe(2);
    await recipient.page.setViewportSize({ width: 390, height: 844 });
    await expect(
      recipient.page.getByRole('button', { name: recipient.t('common.close'), exact: true })
    ).toBeInViewport();
    await expect(
      recipient.page.getByRole('button', { name: recipient.t('world.messages.send'), exact: true })
    ).toBeInViewport();
    const violations = await new AxeBuilder({ page: recipient.page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(
      violations.violations.map(item => ({
        id: item.id,
        nodes: item.nodes.map(node => node.target),
      }))
    ).toEqual([]);
    await recipient.page.screenshot({ path: info.outputPath('world-messages-mobile.png') });
    await recipient.page.setViewportSize({ width: 844, height: 390 });
    await expect(
      recipient.page.getByRole('button', { name: recipient.t('common.close'), exact: true })
    ).toBeInViewport();
    await expect(
      recipient.page.getByRole('button', { name: recipient.t('world.messages.send'), exact: true })
    ).toBeInViewport();
    await recipient.page.keyboard.press('Escape');
    await expect(
      recipient.page.getByRole('button', {
        name: recipient.t('world.messages.action'),
        exact: true,
      })
    ).toBeFocused();
    await sender.page.bringToFront();
    await sender.page.screenshot({ path: info.outputPath('world-messages-desktop.png') });
    expect(sends).toBe(2);
    expect(failures).toEqual([]);
    expect(escaped).toEqual([]);
  } finally {
    try {
      for (const visitor of visitors) {
        await visitor.page.bringToFront();
        await visitor.page.keyboard.press('Escape');
        const leave = visitor.page.getByRole('button', {
          name: visitor.t('world.session.leave'),
          exact: true,
        });
        if (await leave.count()) await leave.last().click();
      }
    } finally {
      await closeWorldDevices(devices);
    }
  }
});

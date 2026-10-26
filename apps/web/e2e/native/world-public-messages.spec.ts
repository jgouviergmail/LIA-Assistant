import { createWorldDevice, closeWorldDevices, type WorldDevice } from '../fixtures/world-device';
import { worldProofUrl } from './world-route';
/** Real isolated SQL/Redis delivery; provider substitution only accepts a fixed proof phrase. */
import { test, expect, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import fr from '../../locales/fr/translation.json';
import en from '../../locales/en/translation.json';
import es from '../../locales/es/translation.json';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { enterWorld, setNativeWorldName } from '../fixtures/world-admission';

test('public audience reaches present people in their own language, stays distinct from private chat and has no newcomer replay', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(150000);
  // The native config requires an explicit isolated origin. The proof-only
  // session endpoint below must succeed before any world message is sent;
  // ordinary LIA does not mount it, and the guarded host has inert translators.
  if (!baseURL) throw new Error('Explicit disposable QA required');
  const proofBaseURL = baseURL;
  const visitors: { context: BrowserContext; page: Page; locale: typeof en }[] = [];
  const devices: WorldDevice[] = [];
  const errors: string[] = [];
  const bodies: unknown[] = [];
  const source = 'Bonjour, ravi de te rencontrer.';
  async function join(index: number, locale: typeof en, language: string, name: string) {
    const device = await createWorldDevice(browser, { baseURL, serviceWorkers: 'block' });
    devices.push(device);
    const context = device.context;
    const page = await context.newPage();
    const visitor = { context, page, locale };
    visitors.push(visitor);
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.url().endsWith('/world/messages/public')) bodies.push(request.postDataJSON());
    });
    const signed = await context.request.post('/api/v1/world-proof/session', {
      headers: { Origin: new URL(proofBaseURL).origin },
      data: { index },
    });
    expect(signed.status()).toBe(200);
    await installOfflineFonts(page);
    await setNativeWorldName(page, name);
    await page.goto(worldProofUrl(proofBaseURL, language).href);
    await enterWorld(page);
    const chat = page.getByRole('button', { name: locale.world.messages.action, exact: true });
    const takeover = page.getByRole('button', { name: locale.world.session.takeover, exact: true });
    await expect(chat.or(takeover)).toBeVisible();
    if (await takeover.isVisible()) await takeover.click();
    await expect(chat).toBeEnabled();
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    return visitor;
  }
  async function publicThread(visitor: (typeof visitors)[number]) {
    await visitor.page.bringToFront();
    await visitor.page
      .getByRole('button', { name: visitor.locale.world.messages.action, exact: true })
      .click();
    await visitor.page
      .getByRole('navigation')
      .getByRole('button')
      .filter({ hasText: visitor.locale.world.public.title })
      .click();
    await expect(
      visitor.page.getByRole('log', { name: visitor.locale.world.public.caption })
    ).toBeVisible();
  }
  try {
    const sender = await join(1, fr, 'fr', 'Camille');
    const receiver = await join(2, en, 'en', 'Robin');
    const third = await join(8, en, 'en', 'Morgan');
    for (const person of [sender, receiver, third]) await publicThread(person);
    await sender.page.bringToFront();
    const field = sender.page.getByRole('textbox', { name: fr.world.messages.message });
    await field.fill(source);
    const send = sender.page.getByRole('button', { name: fr.world.messages.send, exact: true });
    await expect(send).toBeDisabled();
    await sender.page.getByRole('checkbox').check();
    const acknowledgment = sender.page.waitForResponse(r =>
      r.url().endsWith('/world/messages/public')
    );
    await send.click();
    const response = await acknowledgment;
    expect(response.status()).toBe(202);
    const accepted: unknown = await response.json();
    if (
      !accepted ||
      typeof accepted !== 'object' ||
      !('id' in accepted) ||
      typeof accepted.id !== 'string'
    )
      throw new Error('Owned acknowledgment missing');
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({
      audience: 'public',
      text: source,
      translation_consent: true,
    });
    expect(bodies[0]).not.toHaveProperty('recipient');
    for (const person of [receiver, third]) {
      await person.page.bringToFront();
      const article = person.page.locator('[data-world-message="' + accepted.id + '"]');
      await expect(article.getByText('Hello, pleased to meet you.', { exact: true })).toBeVisible();
      expect(await person.page.getByRole('log').textContent()).not.toContain(source);
      await expect(person.page.locator('[data-world-speech="public"]')).toContainText(
        'Hello, pleased to meet you.'
      );
    }
    await sender.page.bringToFront();
    await expect(sender.page.locator('[data-world-message="' + accepted.id + '"]')).toContainText(
      source
    );
    await expect(field).toHaveValue('');
    // Public and private drafts, consent and reading contexts stay independent.
    await sender.page
      .getByRole('navigation')
      .getByRole('button')
      .filter({ hasText: 'Robin' })
      .filter({ has: sender.page.getByText(fr.world.messages.present, { exact: true }) })
      .click();
    await expect(sender.page.getByRole('checkbox')).not.toBeChecked();
    await field.fill('Ce message reste privé.');
    await sender.page.getByRole('checkbox').check();
    const privateAck = sender.page.waitForResponse(r => r.url().endsWith('/world/messages/send'));
    await send.click();
    expect((await privateAck).status()).toBe(202);
    await sender.page
      .getByRole('navigation')
      .getByRole('button')
      .filter({ hasText: fr.world.public.title })
      .click();
    expect(await sender.page.getByRole('log').textContent()).not.toContain(
      'Ce message reste privé.'
    );
    expect(await third.page.getByRole('log').textContent()).not.toContain(
      'Ce message reste privé.'
    );
    const newcomer = await join(4, es, 'es', 'Sol');
    await publicThread(newcomer);
    expect(await newcomer.page.locator('[data-world-message="' + accepted.id + '"]').count()).toBe(
      0
    );
    expect(await newcomer.page.locator('[data-world-speech="public"]').count()).toBe(0);
    await receiver.page.bringToFront();
    await receiver.page.setViewportSize({ width: 320, height: 700 });
    await expect(
      receiver.page.getByRole('button', { name: en.world.messages.send, exact: true })
    ).toBeInViewport();
    await expect(
      receiver.page.getByRole('button', { name: en.common.close, exact: true })
    ).toBeInViewport();
    await receiver.page.screenshot({ path: info.outputPath('public-mobile.png') });
    const axe = await new AxeBuilder({ page: receiver.page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(axe.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
    await receiver.page.setViewportSize({ width: 844, height: 390 });
    await expect(
      receiver.page.getByRole('button', { name: en.world.messages.send, exact: true })
    ).toBeInViewport();
    await sender.page.bringToFront();
    await sender.page.screenshot({ path: info.outputPath('public-desktop.png') });
    await expect(sender.page.locator('[data-world-speech="public"]')).toHaveCount(0, {
      timeout: 6500,
    });
    expect(bodies).toHaveLength(1);
    expect(errors).toEqual([]);
  } finally {
    try {
      for (const person of visitors) {
        if (person.page.isClosed()) continue;
        await person.page.keyboard.press('Escape');
        const leave = person.page.getByRole('button', {
          name: person.locale.world.session.leave,
          exact: true,
        });
        if (await leave.isVisible()) await leave.click();
      }
    } finally {
      await closeWorldDevices(devices);
    }
  }
});

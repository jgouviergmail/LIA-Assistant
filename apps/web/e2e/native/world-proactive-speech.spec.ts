import { createWorldDevice, closeWorldDevices } from '../fixtures/world-device';
import { worldProofUrl } from './world-route';
/** Inert proactive publication through real isolated Redis -> native SSE -> game presenter. */
import { test, expect } from './fixtures';
import { randomUUID } from 'node:crypto';
import fr from '../../locales/fr/translation.json';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { enterWorld } from '../fixtures/world-admission';

test('LIA approaches for an owner-only native proactive opening, waits for the panel and expires', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(90000);
  // Native config requires an explicit isolated origin; proof-session success
  // below fences the fixture from ordinary application accounts.
  if (!baseURL) throw new Error('Explicit disposable QA required');
  const context = await browser.newContext({ baseURL });
  const otherDevice = await createWorldDevice(browser, { baseURL });
  const other = otherDevice.context;
  const page = await context.newPage(),
    peer = await other.newPage();
  const observed: { publicId: string; scope: { epoch: string; controller: string } | null } = {
    publicId: '',
    scope: null,
  };
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    socket.on('framereceived', event => {
      const value: unknown = JSON.parse(String(event.payload));
      if (
        value &&
        typeof value === 'object' &&
        'you' in value &&
        value.you &&
        typeof value.you === 'object' &&
        'id' in value.you &&
        typeof value.you.id === 'string'
      )
        observed.publicId = value.you.id;
    });
  });
  peer.on('request', request => {
    if (!request.url().endsWith('/world/messages/read')) return;
    const value: unknown = request.postDataJSON();
    if (
      value &&
      typeof value === 'object' &&
      'epoch' in value &&
      'controller' in value &&
      typeof value.epoch === 'string' &&
      typeof value.controller === 'string'
    )
      observed.scope = { epoch: value.epoch, controller: value.controller };
  });
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    const anonymous = await context.request.post('/api/v1/world-proof/proactive', {
      headers: { Origin: new URL(baseURL).origin },
    });
    expect(anonymous.status()).toBe(401);
    for (const [ctx, index, p] of [
      [context, 1, page],
      [other, 7, peer],
    ] as const) {
      const signed = await ctx.request.post('/api/v1/world-proof/session', {
        headers: { Origin: new URL(baseURL).origin },
        data: { index },
      });
      expect(signed.status()).toBe(200);
      await installOfflineFonts(p);
      await p.goto(worldProofUrl(baseURL, 'fr').href);
      await enterWorld(p);
      await expect(p.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    }
    await page.bringToFront();
    await page.getByRole('button', { name: fr.world.messages.action, exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    const crossOrigin = await context.request.post('/api/v1/world-proof/proactive', {
      headers: { Origin: 'http://untrusted.example' },
    });
    expect(crossOrigin.status()).toBe(403);
    const suppliedPayload = await context.request.post('/api/v1/world-proof/proactive', {
      headers: { Origin: new URL(baseURL).origin },
      data: { recipient: 'another-account', content: 'not-an-accepted-fixture' },
    });
    expect(suppliedPayload.status()).toBe(403);
    const suppliedDestination = await context.request.post(
      '/api/v1/world-proof/proactive?recipient=another-account',
      { headers: { Origin: new URL(baseURL).origin } }
    );
    expect(suppliedDestination.status()).toBe(403);
    // The guarded proof route accepts no payload or destination and invokes the real publisher.
    const opening = await context.request.post('/api/v1/world-proof/proactive', {
      headers: { Origin: new URL(baseURL).origin },
    });
    expect(opening.status()).toBe(204);
    await page.waitForTimeout(1800);
    expect(await page.locator('[data-world-speech="lia"]').count()).toBe(0);
    await page.keyboard.press('Escape');
    const line = page.locator('[data-world-speech="lia"]');
    await expect(line).toContainText('Une idée pour ta promenade', { timeout: 60000 });
    expect(await peer.locator('[data-world-speech="lia"]').count()).toBe(0);
    // Simultaneous private speech must stay separate from LIA's proactive bubble.
    await expect.poll(() => Boolean(observed.scope && observed.publicId)).toBe(true);
    const scope = observed.scope;
    if (!scope) throw new Error('Missing owned message scope');
    const headers = { Origin: new URL(baseURL).origin };
    const inbox = await peer.request.post('/api/v1/world/messages/read', { headers, data: scope });
    expect(inbox.status()).toBe(200);
    const clock = await inbox.json();
    const sent = await peer.request.post('/api/v1/world/messages/send', {
      headers,
      data: {
        ...scope,
        id: randomUUID(),
        recipient: observed.publicId,
        text: 'On se retrouve près de la fontaine ?',
        created_at: clock.server_time,
        translation_consent: false,
      },
    });
    expect(sent.status()).toBe(202);
    await expect(page.locator('[data-world-speech="private"]')).toContainText(
      'On se retrouve près de la fontaine'
    );

    await page.screenshot({ path: info.outputPath('lia-proactive-bubble.png') });
    await expect(line).toHaveCount(0, { timeout: 6500 });
    expect(errors).toEqual([]);
  } finally {
    try {
      for (const p of [page, peer]) {
        if (p.isClosed()) continue;
        await p.keyboard.press('Escape');
        const leave = p.getByRole('button', { name: fr.world.session.leave, exact: true });
        if (await leave.isVisible()) await leave.click();
      }
    } finally {
      await closeWorldDevices([{ context, close: () => context.close() }, otherDevice]);
    }
  }
});

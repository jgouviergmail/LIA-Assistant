/** Native private send → mailbox → both avatar bubbles, with no optimistic echo. */
import { test, expect } from '../fixtures';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { waitForMockGate } from '../fixtures/api-mock';
import { WORLD } from '../../src/features/world/definition';
import type { PrivateMessageWrite, WorldMailbox } from '../../src/features/world/message-protocol';
import en from '../../locales/en/translation.json';

const PEER = '5010c2c2-4bd0-4d21-9c08-b4502db25001';

for (const width of [390, 1280]) {
  test(`private chat shows the owner's and peer's bubbles at width ${width}`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    // This mailbox journey uses the inert notification stream. Do not initialize
    // an environment-configured Firebase SDK: Playwright WebKit exposes
    // Notification but lacks the push APIs that SDK requires.
    await page.addInitScript(() => {
      Reflect.deleteProperty(window, 'Notification');
    });
    await page.setViewportSize({ width, height: 900 });
    const user = await authenticate();
    await installInertWorldAdmission(page, user.id, {
      actors: [
        {
          id: PEER,
          alias: 'Camille',
          position: { x: WORLD.spawn.x + 1, y: WORLD.spawn.y },
          facing: 1,
          walking: false,
        },
      ],
    });
    const mailbox: WorldMailbox = {
      server_time: Date.now() / 1000,
      ttl_seconds: 1800,
      truncated: false,
      messages: [],
    };
    let accept = () => {};
    const accepted = new Promise<void>(resolve => {
      accept = resolve;
    });
    await mockApi([
      {
        url: '**/api/v1/world/messages/read',
        handler: route => route.fulfill({ json: { ...mailbox, server_time: Date.now() / 1000 } }),
      },
      {
        url: '**/api/v1/world/messages/send',
        handler: async (route, signal) => {
          const sent: PrivateMessageWrite = route.request().postDataJSON();
          expect(sent.recipient).toBe(PEER);
          if (!(await waitForMockGate(accepted, signal))) return;
          const now = Date.now() / 1000;
          mailbox.messages = [
            {
              id: sent.id,
              sender_id: user.id,
              sender_alias: 'Explorer',
              recipient_id: PEER,
              recipient_alias: 'Camille',
              outgoing: true,
              original: sent.text,
              text: sent.text,
              language: 'en',
              status: 'pending',
              created_at: now,
              expires_at: now + 1800,
              receipt: null,
            },
            {
              id: '5010c2c2-4bd0-4d21-9c08-b4502db25002',
              sender_id: PEER,
              sender_alias: 'Camille',
              recipient_id: user.id,
              recipient_alias: 'Explorer',
              outgoing: false,
              original: 'Une réponse privée',
              text: 'A private reply',
              language: 'en',
              status: 'translated',
              created_at: now,
              expires_at: now + 1800,
              receipt: null,
            },
          ];
          await route.fulfill({ json: { id: sent.id, status: 'pending' } });
        },
      },
    ]);
    await page.goto('/en/dashboard/world');
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    if (width < 768)
      await page.getByRole('button', { name: en.world.messages.action, exact: true }).click();
    const quick = page.getByRole('region', { name: en.world.compact.title, exact: true });
    const field = quick.getByRole('textbox', { name: en.world.messages.message, exact: true });
    await expect(quick.getByRole('log')).toBeVisible();
    await expect(quick.locator('option:checked')).toHaveText('Auto · Private · Camille');
    await field.fill('My private hello');
    await quick.getByRole('button', { name: en.world.messages.send, exact: true }).click();
    await page.getByRole('dialog').getByRole('checkbox').check();
    await page.keyboard.press('Escape');
    const request = page.waitForRequest('**/api/v1/world/messages/send');
    await quick.getByRole('button', { name: en.world.messages.send, exact: true }).click();
    await request;
    await expect(page.locator('[data-world-speech]')).toHaveCount(0);
    accept();
    const ownBubble = page.locator(
      `[data-world-speech="private"][data-world-speaker="${user.id}"]`
    );
    const peerBubble = page.locator(`[data-world-speech="private"][data-world-speaker="${PEER}"]`);
    await expect(ownBubble).toHaveText('Explorer: My private hello');
    await expect(peerBubble).toHaveText('Camille: A private reply');
    await expect(field).toHaveValue('');
    await page.screenshot({ path: info.outputPath(`private-bubbles-${width}.png`) });
    await expect(page.locator('[data-world-speech]')).toHaveCount(0, { timeout: 7000 });
    await expect(quick.getByRole('log')).toContainText('My private hello');
    expect(errors).toEqual([]);
  });
}

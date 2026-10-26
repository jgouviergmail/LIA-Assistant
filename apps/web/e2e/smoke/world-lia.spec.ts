/** Browser integration of the SAME pending-approval contract in world mode. */
import { test, expect } from '../fixtures';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { baseRoutes, PENDING_TOOL_CONFIRMATION, sseDone } from '../fixtures/chat-approval';

for (const theme of ['light', 'dark'] as const)
  test(
    'world LIA: opens without sending, restores the pending approval and submits its explicit cancellation in ' +
      theme,
    async ({ page, authenticate, mockApi }, info) => {
      await page.addInitScript(value => localStorage.setItem('theme', value), theme);
      const user = await authenticate();
      await mockApi(baseRoutes(PENDING_TOOL_CONFIRMATION, sseDone));
      await installInertWorldAdmission(page, user.id);
      const submissions: unknown[] = [];
      page.on('request', request => {
        if (request.method() === 'POST' && request.url().includes('/agents/chat/stream'))
          submissions.push(request.postDataJSON());
      });
      await page.goto(
        '/fr/dashboard/world?intent=DO_NOT_SEND_WORLD_TEST&draft=HOST_ONLY_TEST&iid=world-host-only'
      );
      await expect(page.getByRole('textbox', { name: 'Votre pseudonyme' })).toHaveCount(0);
      await enterWorld(page);
      const talk = page.getByRole('button', { name: 'Parler à LIA', exact: true });
      await expect(talk).toBeEnabled();
      await talk.click();
      const card = page.locator('section[aria-label="Approbation requise"]');
      await expect(card).toBeVisible();
      expect(submissions).toEqual([]);
      await expect(card.getByRole('button', { name: 'Confirmer', exact: true })).toBeEnabled();
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
        await expect(card).toBeVisible();
        await expect
          .poll(() =>
            page.locator('canvas.world-canvas').evaluate((canvas: HTMLCanvasElement) => {
              const box = canvas.getBoundingClientRect();
              const scale = canvas.width / box.width;
              return Math.abs(canvas.height - box.height * scale) < 3;
            })
          )
          .toBe(true);
        await expect
          .poll(() =>
            card.evaluate(element => {
              // The sticky band must mask the scrolling messages, including under
              // warning/critical cards whose tint alone is intentionally translucent.
              const footer = element.parentElement;
              if (!footer || getComputedStyle(footer).position !== 'sticky')
                throw new Error('Approval is outside its sticky band');
              const canvas = document.createElement('canvas');
              canvas.width = canvas.height = 1;
              const context = canvas.getContext('2d');
              if (!context) throw new Error('Missing colour conversion');
              context.fillStyle = getComputedStyle(footer).backgroundColor;
              context.fillRect(0, 0, 1, 1);
              return context.getImageData(0, 0, 1, 1).data[3];
            })
          )
          .toBe(255);
        await page.screenshot({
          path: info.outputPath('world-lia-hitl-' + theme + '-' + width + '.png'),
        });
      }
      await card.getByRole('button', { name: 'Annuler', exact: true }).click();
      await expect(card).toHaveCount(0);
      expect(submissions).toHaveLength(1);
      expect(JSON.stringify(submissions)).not.toContain('DO_NOT_SEND_WORLD_TEST');
      expect(JSON.stringify(submissions)).not.toContain('HOST_ONLY_TEST');
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(
        page.getByRole('button', { name: 'Commandes du monde', exact: true })
      ).toBeFocused();
    }
  );

test('world LIA: preserves an unsent draft and keyboard focus through same-owner verification', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  await mockApi(baseRoutes(null, sseDone));
  await installInertWorldAdmission(page, user.id);
  const submissions: string[] = [];
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().includes('/agents/chat/stream'))
      submissions.push(request.url());
  });
  await page.goto('/fr/dashboard/world');
  await expect(page.getByRole('textbox', { name: 'Votre pseudonyme' })).toHaveCount(0);
  await enterWorld(page);
  await page.getByRole('button', { name: 'Parler à LIA', exact: true }).click();
  const composer = page.locator('textarea');
  await expect(composer).toBeEnabled();
  await composer.fill('BROUILLON PRIVÉ NON ENVOYÉ');
  const verified = page.waitForResponse(response => response.url().endsWith('/auth/me'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  expect((await verified).status()).toBe(200);
  await expect(composer).toBeVisible();
  await expect(composer).toHaveValue('BROUILLON PRIVÉ NON ENVOYÉ');
  await expect(composer).toBeFocused();
  expect(submissions).toEqual([]);
});

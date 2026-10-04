/** A card opens an editable draft; the archived target travels only on explicit send. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

interface Reference {
  language: string;
  html: string;
  metadata: Record<string, unknown>;
}
const references: Reference[] = JSON.parse(
  readFileSync(
    path.join(
      __dirname,
      '../../../api/tests/unit/domains/agents/display/card_composition_corpus.json'
    ),
    'utf8'
  )
);
const messageId = '00000000-0000-4000-8000-00000000c405';

for (const sample of [
  { width: 1280, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
]) {
  test.describe(`card composition at ${sample.width}px`, () => {
    test.use({ hasTouch: sample.width < 500 });
    test(`preservation, reload and explicit send in ${sample.theme}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      const reference = references.find(item => item.language === sample.language);
      if (!reference) throw new Error('Missing backend composition reference');
      const bodies: unknown[] = [];
      await page.setViewportSize({ width: sample.width, height: 1200 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await authenticate({ language: sample.language, response_display_mode: 'cards' });
      await mockApi([
        ...loadedChatRoutes(),
        {
          url: '**/api/v1/conversations/me/messages*',
          json: {
            messages: [
              {
                id: messageId,
                role: 'assistant',
                content: reference.html,
                created_at: '2026-10-03T09:30:00Z',
                message_metadata: reference.metadata,
              },
            ],
            conversation_id: '00000000-0000-4000-8000-00000000c0h1',
            total_count: 1,
            has_more: false,
            next_cursor: null,
          },
        },
        {
          url: '**/api/v1/agents/chat/stream',
          method: 'POST',
          handler: async route => {
            bodies.push(route.request().postDataJSON());
            await route.fulfill({
              status: 200,
              contentType: 'text/event-stream',
              body:
                'data: {"type":"token","content":"Draft requested"}\n\n' +
                'data: {"type":"done","content":"","metadata":{}}\n\n',
            });
          },
        },
      ]);
      await page.goto(`/${sample.language}/dashboard/chat`);
      await waitForHydration(page);
      await awaitStyledPage(page, 'card composition');
      await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });
      await page.evaluate(theme => {
        document.documentElement.classList.toggle('dark', theme !== 'light');
        document.documentElement.toggleAttribute('data-oled', theme === 'oled');
      }, sample.theme);
      const input = page.getByRole('textbox').first();
      const reply = page.locator('.lia-action-btn[data-action="reply"]');
      const forward = page.locator('.lia-action-btn[data-action="forward"]');
      await expect(reply).toBeEnabled();
      await input.fill('Unfinished personal draft');
      await reply.focus();
      await reply.press('Enter');
      const dialog = page.getByRole('alertdialog');
      await expect(dialog).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(input).toHaveValue('Unfinished personal draft');
      expect(bodies).toHaveLength(0);
      await input.fill('');
      if (sample.width < 500) await reply.tap();
      else await reply.click();
      const chip = page.getByRole('group', {
        name: sample.language === 'fr' ? 'Carte sélectionnée' : 'Selected card',
      });
      await expect(chip).toBeVisible();
      await expect(input).not.toHaveValue('');
      await expect(input).not.toHaveValue(/email_reference|source-run/);
      expect(bodies).toHaveLength(0);
      expect((await reply.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      await input.fill('My edited reply');
      await expect
        .poll(() =>
          page.evaluate(() =>
            Object.keys(localStorage).some(
              key =>
                key.startsWith('lia.chatDraft.') &&
                localStorage.getItem(key)?.includes('My edited reply')
            )
          )
        )
        .toBe(true);
      await page.reload();
      await waitForHydration(page);
      await awaitStyledPage(page, 'restored composition');
      await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });
      await page.evaluate(theme => {
        document.documentElement.classList.toggle('dark', theme !== 'light');
        document.documentElement.toggleAttribute('data-oled', theme === 'oled');
      }, sample.theme);
      await expect(input).toHaveValue('My edited reply');
      await expect(chip).toBeVisible();
      expect(bodies).toHaveLength(0);
      await expectNoOverflow(page, `composition ${sample.width}`);
      const accessibility = await new AxeBuilder({ page })
        .include('.lia-response-wrapper')
        .include('[role="group"]')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect(accessibility.violations).toEqual([]);
      await page.screenshot({ path: `/repo/.tmp/analysis/card-composition-${sample.theme}.png` });
      await input.press('Enter');
      await expect.poll(() => bodies.length).toBe(1);
      expect(bodies[0]).toMatchObject({
        message: 'My edited reply',
        context: {
          card_composition: {
            version: 1,
            message_id: messageId,
            run_id: 'source-run',
            registry_id: 'email_reference',
            action: 'reply',
          },
        },
      });
      await expect(chip).not.toBeVisible();
      await forward.click();
      await expect(chip).toBeVisible();
      await chip.getByRole('button').click();
      await expect(chip).not.toBeVisible();
      await expect(input).not.toHaveValue('');
      expect(bodies).toHaveLength(1);
    });
  });
}

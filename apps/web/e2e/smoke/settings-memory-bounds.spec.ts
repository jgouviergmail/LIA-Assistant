/**
 * The memory form states the bound the API enforces, in the real locale strings.
 *
 * In production on 2026-11-06, a few words added to a 495-character memory were refused
 * five times with a bare error. The unit tests echo translation keys, so only a browser
 * can show the figures the person actually reads.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, idleNotificationStream } from '../fixtures';
import { surfaceMemoryLimits, surfaceRoutes } from '../fixtures/settings-surfaces';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const french = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
) as {
  common: { save: string; actions_for: string };
  memories: {
    edit: string;
    update_success: string;
    field_content: string;
    text_too_long: string;
    categories: { sensitivity: string };
  };
};

const memoryId = '00000000-0000-4000-8000-000000000495';
const stored = 'x'.repeat(495);
const memory = {
  id: memoryId,
  content: stored,
  category: 'sensitivity',
  emotional_weight: -6,
  trigger_topic: 'fiction',
  usage_nuance: '',
  importance: 0.9,
  pinned: true,
};
const list = {
  items: [memory],
  total: 1,
  by_category: { sensitivity: 1 },
  limits: surfaceMemoryLimits,
};

for (const width of [1280, 360]) {
  test(`a memory outgrowing its bound says so, and saves once back within it at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    const saved: { content?: string }[] = [];
    await mockApi([
      ...surfaceRoutes,
      idleNotificationStream,
      { url: /\/api\/v1\/memories(?:\?.*)?$/, json: list },
      {
        url: `**/api/v1/memories/${memoryId}`,
        method: 'PATCH',
        handler: async route => {
          const body = route.request().postDataJSON() as { content?: string };
          saved.push(body);
          await route.fulfill({ json: { ...memory, ...body } });
        },
      },
    ]);

    await page.goto('/fr/dashboard/settings?section=memories');
    await awaitStyledPage(page, 'Memories');
    const section = page.locator('#settings-section-memories');
    await section
      .getByRole('button', { name: new RegExp(french.memories.categories.sensitivity) })
      .click();
    if (width < 640) {
      // Below `sm` a row's actions live in its « ⋮ » menu (ADR-208).
      const rowMenu = french.common.actions_for.split('{{')[0];
      await section.getByRole('button', { name: new RegExp(`^${rowMenu}`) }).click();
      await page.getByRole('menuitem', { name: french.memories.edit }).click();
    } else {
      await section.getByRole('button', { name: french.memories.edit }).click();
    }

    const dialog = page.getByRole('dialog');
    const content = dialog.getByLabel(french.memories.field_content);
    const save = dialog.getByRole('button', { name: french.common.save });
    await expect(dialog.getByText('495 / 500')).toBeVisible();
    await expect(save).toBeEnabled();

    // Six more characters: one past the ceiling, with the figure and the way out.
    await content.press('Control+End');
    await page.keyboard.type('plus !');
    await expect(dialog.getByText('501 / 500')).toBeVisible();
    await expect(dialog.getByRole('alert')).toHaveText(
      french.memories.text_too_long.replace('{{max}}', '500')
    );
    await expect(content).toHaveAttribute('aria-invalid', 'true');
    await expect(save).toBeDisabled();
    expect(
      (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations
    ).toEqual([]);
    await expectNoOverflow(page, `Memory form past its bound at ${width}px`);

    // The text was never cut: one character removed is one character back within it.
    await page.keyboard.press('Backspace');
    await expect(dialog.getByText('500 / 500')).toBeVisible();
    await expect(dialog.getByRole('alert')).toHaveCount(0);
    await expect(save).toBeEnabled();
    expect(saved).toEqual([]);

    await save.focus();
    await page.keyboard.press('Enter');

    await expect(dialog).toBeHidden();
    await expect(page.getByText(french.memories.update_success)).toBeVisible();
    expect(saved).toHaveLength(1);
    expect(saved[0].content).toBe(`${stored}plus `);
  });
}

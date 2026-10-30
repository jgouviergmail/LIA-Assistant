/**
 * Relations — the 360° sheet's action bar has two shapes, never a third.
 *
 * Owner report 2026-10-29: the buttons carried their value (« Itinéraire vers
 * 12 rue… »), so the DATA sized them, they wrapped by kind in columns of
 * unequal length, and every width between a phone and a desktop drew a
 * different arrangement. The bar now has short labels and one entry per kind,
 * and exactly two shapes: ONE ROW of equal-width buttons when the sheet can
 * hold it, ONE FULL-WIDTH LIST otherwise.
 *
 * The oracle is the geometry the reader sees, at every width the layout passes
 * through and in the six languages (a row that fits in French is not a row
 * that fits in German): every button the same width, and either every top
 * equal (the row) or every left equal (the list) — anything else is the
 * intermediate state the bar exists to remove. The worst case is served: a
 * connection (« Write »), a card with two mailboxes (a menu), an address and a
 * number with an active telephony connector — five entries.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import type { Locator, Page } from '@playwright/test';

import { test, expect } from '../fixtures';
import { relationContextPayload, relationsData } from '../fixtures/relations';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

/** Frontend-canonical locale segment (zh, never zh-CN). */
const LOCALES = ['fr', 'en', 'de', 'es', 'it', 'zh'] as const;

/** From the WCAG reflow floor to a wide desktop, through every breakpoint between. */
const WIDTHS = [320, 375, 480, 560, 640, 700, 768, 900, 1024, 1280, 1440] as const;

const PERSON = 'Gérard Dupont';

/** The worst case: two mailboxes (so a menu), an address and a number. */
const routes = [
  ...relationsData,
  {
    // AFTER the fixture (LIFO): this answer wins over its `/context`.
    url: '**/api/v1/relations/*/context',
    json: {
      ...relationContextPayload,
      contact: {
        ...relationContextPayload.contact,
        contact: {
          ...relationContextPayload.contact.contact,
          emails: [
            { value: 'gerard@example.com', label: 'work' },
            { value: 'gerard.dupont@example.org', label: 'home' },
          ],
        },
      },
    },
  },
  {
    // An ACTIVE telephony connector: the number is offered a call.
    url: /\/api\/v1\/connectors\?fresh=true$/,
    json: {
      connectors: [
        {
          id: 'telephony-connector',
          connector_type: 'elevenlabs_telephony',
          status: 'active',
          created_at: '2026-10-01T08:00:00Z',
        },
      ],
    },
  },
];

/** The relations strings of one locale, read from the file the app ships. */
function relationsStrings(lng: string): Record<string, string> {
  const file = path.join(__dirname, '..', '..', 'locales', lng, 'translation.json');
  return JSON.parse(readFileSync(file, 'utf-8')).relations;
}

async function openGerard(page: Page) {
  await page.getByRole('main').getByRole('button').filter({ hasText: PERSON }).first().click();
  await expect(page.getByRole('heading', { level: 2, name: PERSON })).toBeVisible({
    timeout: 15_000,
  });
}

/** Every button's box, in tree order. */
async function boxes(bar: Locator) {
  const buttons = bar.getByRole('button');
  const count = await buttons.count();
  const out: { x: number; y: number; width: number; height: number }[] = [];
  for (let index = 0; index < count; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    if (!box) throw new Error(`button ${index} of the bar has no box`);
    out.push(box);
  }
  return out;
}

test.describe('relations — the action bar is a row or a list, never in between', () => {
  for (const lng of LOCALES) {
    test(`two shapes at every width @ ${lng}`, async ({ page, authenticate, mockApi }, info) => {
      const strings = relationsStrings(lng);
      await authenticate();
      await mockApi(routes);
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(`/${lng}/dashboard/relations`);
      await awaitStyledPage(page, `relations list (${lng})`);
      await openGerard(page);

      const bar = page.getByRole('group', {
        name: strings.actions_group.replace('{{name}}', PERSON),
      });
      // Five entries once the card and the connectors have landed.
      await expect(bar.getByRole('button')).toHaveCount(5);
      // The address book's kinds come last, the email one a menu.
      await expect(bar.getByRole('button', { name: strings.action_email })).toHaveAttribute(
        'aria-haspopup',
        'menu'
      );

      const shapes: Record<number, string> = {};
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 });
        // Two frames: the container query and the grid re-lay out on the new width.
        await page.evaluate(
          () =>
            new Promise<void>(resolve =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
            )
        );
        const phase = `action bar @${width} (${lng})`;
        await expectNoOverflow(page, phase);

        const sized = await boxes(bar);
        const widths = sized.map(box => box.width);
        expect(Math.max(...widths) - Math.min(...widths), `${phase}: equal widths`).toBeLessThan(
          1.5
        );
        const tops = new Set(sized.map(box => Math.round(box.y)));
        const lefts = new Set(sized.map(box => Math.round(box.x)));
        const shape = tops.size === 1 ? 'row' : lefts.size === 1 ? 'list' : 'mixed';
        expect(shape, `${phase}: one row or one list`).not.toBe('mixed');
        shapes[width] = shape;

        // Above the debrief at every width (owner request 2026-10-29).
        const barBox = await bar.boundingBox();
        const debrief = await page
          .getByRole('heading', { name: strings.debrief_title, exact: true })
          .boundingBox();
        if (!barBox || !debrief) throw new Error(`${phase}: bar or debrief not on screen`);
        expect(barBox.y + barBox.height, `${phase}: bar above the debrief`).toBeLessThanOrEqual(
          debrief.y
        );
      }
      // The list on a phone, the row on a desktop: the two shapes both exist.
      expect(shapes[320]).toBe('list');
      expect(shapes[1280]).toBe('row');
      // Monotone: once the row fits, every wider width keeps it.
      const firstRow = WIDTHS.findIndex(width => shapes[width] === 'row');
      expect(WIDTHS.slice(firstRow).every(width => shapes[width] === 'row')).toBe(true);
      await info.attach(`shapes-${lng}.json`, {
        body: JSON.stringify(shapes, null, 2),
        contentType: 'application/json',
      });
    });
  }

  test('the menu lists both mailboxes with their labels, inside a phone screen', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const strings = relationsStrings('fr');
    await authenticate();
    await mockApi(routes);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/fr/dashboard/relations');
    await awaitStyledPage(page, 'relations list (menu)');
    await openGerard(page);

    const bar = page.getByRole('group', {
      name: strings.actions_group.replace('{{name}}', PERSON),
    });
    await bar.getByRole('button', { name: strings.action_email }).click();
    const items = page.getByRole('menuitem');
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toContainText('gerard@example.com');
    await expect(items.nth(0)).toContainText('travail');
    await expect(items.nth(1)).toContainText('gerard.dupont@example.org');
    await expect(items.nth(1)).toContainText('domicile');
    await expectNoOverflow(page, 'action bar menu @375 (fr)');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu')).toHaveCount(0);
  });
});

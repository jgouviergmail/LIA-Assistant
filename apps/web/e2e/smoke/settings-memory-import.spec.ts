/**
 * Memories — an export is brought back from the toolbar, and every entry is accounted for.
 *
 * Hermetic, in a real engine, at a desktop and a phone width. Import stands
 * beside Export on the memories toolbar (and the bar still holds on one phone
 * screen), as ONE control — the file picker behind it is no second button for
 * a screen reader; the file picked is sent as it is; while it is read the
 * action is busy and keeps the focus, never disabled under the person's
 * hands; the answer is said whole, in the real locale strings and with the
 * API's own counts; and the list is read again, since what was created has
 * identifiers only the API knows. A file the API refuses is said in the API's
 * own sentence.
 */
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { test, expect, idleNotificationStream } from '../fixtures';
import { surfaceMemoryLimits, surfaceRoutes } from '../fixtures/settings-surfaces';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const french = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
) as {
  memories: {
    export: string;
    import: string;
    import_file: string;
    import_imported: string;
    import_already_present: string;
    import_invalid: string;
  };
};
const copy = french.memories;

const memory = {
  id: '00000000-0000-4000-8000-000000000a01',
  content: 'Préfère le thé au café',
  category: 'preference',
  emotional_weight: 2,
  trigger_topic: 'boissons',
  usage_nuance: '',
  importance: 0.6,
  pinned: false,
};
const list = (count: number) => ({
  items: Array.from({ length: count }, (_, index) => ({
    ...memory,
    id: `00000000-0000-4000-8000-000000000a0${index + 1}`,
    content: `${memory.content} (${index + 1})`,
  })),
  total: count,
  by_category: { preference: count },
  limits: surfaceMemoryLimits,
});
const EXPORT = Buffer.from('content,category\nUn fait,personal\nUn autre,personal\n');

for (const width of [1280, 360]) {
  test(`an export is imported from the toolbar and every entry is accounted for at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    let reads = 0;
    const sent: string[] = [];
    // The import answers when the test lets it: what the action looks like
    // WHILE it runs is part of the journey.
    let answer: () => void = () => {};
    const answered = new Promise<void>(resolve => {
      answer = resolve;
    });
    await mockApi([
      ...surfaceRoutes,
      idleNotificationStream,
      {
        url: /\/api\/v1\/memories(?:\?.*)?$/,
        handler: async route => {
          reads += 1;
          await route.fulfill({ json: list(sent.length ? 3 : 1) });
        },
      },
      {
        url: '**/api/v1/memories/import',
        method: 'POST',
        handler: async route => {
          sent.push(/filename="([^"]+)"/.exec(route.request().postData() ?? '')?.[1] ?? '');
          await answered;
          await route.fulfill({
            json: { total: 4, imported: 2, already_present: 1, duplicates: 0, invalid: 1 },
          });
        },
      },
    ]);

    await page.goto('/fr/dashboard/settings?section=memories');
    await awaitStyledPage(page, 'Memories import');
    const section = page.locator('#settings-section-memories');
    const action = section.getByRole('button', { name: copy.import, exact: true });
    // Beside Export, at every width: folded away it would read as absent.
    await expect(section.getByRole('button', { name: copy.export })).toBeVisible();
    await expect(action).toBeVisible();
    // ONE control imports, for a screen reader as for the eye: the file picker
    // behind the action is not a second button nobody can reach by keyboard.
    await expect.soft(section.getByRole('button', { name: /import/i })).toHaveCount(1);
    await expectNoOverflow(page, `Memories toolbar with Import at ${width}px`);
    expect(
      (
        await new AxeBuilder({ page })
          .include('#settings-section-memories')
          .withTags(['wcag2a', 'wcag2aa'])
          .analyze()
      ).violations
    ).toEqual([]);
    const readsBefore = reads;

    // A keyboard user activates the action, picks a file, and is back on it.
    await action.focus();
    await section
      .getByLabel(copy.import_file)
      .setInputFiles({ name: 'memories.csv', mimeType: 'text/csv', buffer: EXPORT });

    // While the import runs the action is busy, never removed: the person
    // keeps their place instead of landing back on the top of the page.
    await expect(action).toHaveAttribute('aria-busy', 'true');
    await expect(action).toBeFocused();
    answer();
    await expect(action).not.toHaveAttribute('aria-busy', 'true');
    await expect(action).toBeFocused();

    // Every entry of the file is accounted for, with the API's own counts.
    const summary = [
      copy.import_imported.replace('{{n}}', '2'),
      copy.import_already_present.replace('{{n}}', '1'),
      copy.import_invalid.replace('{{n}}', '1'),
    ].join(' · ');
    await expect(page.getByText(summary)).toBeVisible();
    expect(sent).toEqual(['memories.csv']);
    // What was created has identifiers only the API knows: the list is read again.
    await expect.poll(() => reads).toBeGreaterThan(readsBefore);
  });
}

test('a file the API refuses is said in the API’s own sentence', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  const refusal = "Ce fichier n'est pas un export de mémoires LIA (CSV ou JSON)";
  await mockApi([
    ...surfaceRoutes,
    idleNotificationStream,
    { url: /\/api\/v1\/memories(?:\?.*)?$/, json: list(1) },
    {
      url: '**/api/v1/memories/import',
      method: 'POST',
      handler: async route => {
        await route.fulfill({ status: 400, json: { detail: refusal } });
      },
    },
  ]);

  await page.goto('/fr/dashboard/settings?section=memories');
  await awaitStyledPage(page, 'Memories import refusal');
  await page
    .locator('#settings-section-memories')
    .getByLabel(copy.import_file)
    .setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('a note') });

  await expect(page.getByText(refusal)).toBeVisible();
});

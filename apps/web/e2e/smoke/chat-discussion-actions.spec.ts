/**
 * The answers a discussion LIA opened offers, in a real browser (owner request,
 * 2026-10-21): the bubble row's own chips — same box, same size as Copy — on a
 * ground a shade deeper, so they read as the discussion's without a new colour.
 *
 * The oracle is the painted pixel, not a class name: each chip is captured and its
 * ground (a patch inside its border, clear of its icon) is compared with the Copy
 * chip's, in the light, dark and OLED themes.
 */
import type { Locator, Page } from '@playwright/test';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { scanPage } from '../a11y/scan';
import { prepareTheme, awaitStyledPage, expectNoOverflow } from './overflow-report';

const OPENING_ID = '10000000-0000-4000-8000-0000000000d1';

const samples = [
  {
    language: 'fr',
    width: 1280,
    theme: 'light',
    copy: 'Copier le message',
    useful: 'Merci, cela me parle',
    reply: 'Répondre',
  },
  {
    language: 'en',
    width: 390,
    theme: 'dark',
    copy: 'Copy message',
    useful: 'Thanks, this resonates',
    reply: 'Reply',
  },
  {
    language: 'de',
    width: 320,
    theme: 'oled',
    copy: 'Nachricht kopieren',
    useful: 'Danke, das spricht mich an',
    reply: 'Antworten',
  },
] as const;

/** The relative luminance of a chip's ground: a 3 × 3 patch just inside its border. */
async function groundLuminance(page: Page, chip: Locator): Promise<number> {
  const png = await chip.screenshot();
  const probe = await page.context().newPage();
  try {
    return await probe.evaluate(
      async source => {
        const image = new Image();
        image.src = source;
        await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = image.width;
        canvas.height = image.height;
        const context = canvas.getContext('2d')!;
        context.drawImage(image, 0, 0);
        const ratio = image.width / 26;
        const at = Math.max(2, Math.round(3 * ratio));
        const data = context.getImageData(at, at, 3, 3).data;
        const channel = (value: number) => {
          const c = value / 255;
          return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        };
        let total = 0;
        for (let index = 0; index < data.length; index += 4)
          total +=
            0.2126 * channel(data[index]) +
            0.7152 * channel(data[index + 1]) +
            0.0722 * channel(data[index + 2]);
        return total / (data.length / 4);
      },
      `data:image/png;base64,${png.toString('base64')}`
    );
  } finally {
    await probe.close();
  }
}

for (const sample of samples) {
  test(`discussion answers ${sample.language} ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({ language: sample.language, theme: sample.theme });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-0000000000d2',
              role: 'assistant',
              content: 'Comment s’est passée la randonnée de samedi ?',
              created_at: '2026-10-21T10:00:00Z',
              message_metadata: {
                type: 'proactive_discussion',
                discussion_id: OPENING_ID,
                discussion_feedback: null,
                discussion_pause_hours: 24,
                feedback_enabled: false,
              },
            },
          ],
          conversation_id: '00000000-0000-4000-8000-000000000011',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto(`/${sample.language}/dashboard/chat`, { waitUntil: 'domcontentloaded' });
    await waitForHydration(page);
    await awaitStyledPage(page, `discussion answers ${sample.theme}`);
    const copy = page.getByRole('button', { name: sample.copy, exact: true });
    const useful = page.getByRole('button', { name: sample.useful, exact: true });
    const reply = page.getByRole('button', { name: sample.reply, exact: true });
    await expect(useful).toBeVisible();
    await expect(reply).toBeVisible();
    // The same box as the row's own actions.
    const [copyBox, usefulBox] = [await copy.boundingBox(), await useful.boundingBox()];
    expect(usefulBox!.height).toBeCloseTo(copyBox!.height, 0);
    expect(usefulBox!.width).toBeCloseTo(copyBox!.width, 0);
    // At the RIGHT end of the bubble's actions (owner decision 2026-10-24): the
    // answers end where the row ends, on Copy's line when the row has room.
    const group = useful.locator('xpath=..');
    const [groupBox, rowBox] = [
      await group.boundingBox(),
      await group.locator('xpath=..').boundingBox(),
    ];
    expect(Math.abs(groupBox!.x + groupBox!.width - (rowBox!.x + rowBox!.width))).toBeLessThan(2);
    if (sample.width >= 1024) expect(Math.abs(usefulBox!.y - copyBox!.y)).toBeLessThan(2);
    // A shade deeper, never a different family: darker than Copy, by a little.
    const [classic, deeper] = [
      await groundLuminance(page, copy),
      await groundLuminance(page, useful),
    ];
    test.info().annotations.push({
      type: 'luminance',
      description: `${sample.theme}: copy ${classic.toFixed(4)} discussion ${deeper.toFixed(4)}`,
    });
    if (sample.theme === 'oled') expect(deeper).toBeLessThanOrEqual(classic + 0.002);
    else expect(deeper).toBeLessThan(classic);
    expect(classic - deeper).toBeLessThan(0.12);
    await expectNoOverflow(page, `discussion answers ${sample.theme}`);
    const scan = await scanPage(page, test.info(), `discussion answers ${sample.theme}`);
    expect(scan.blocking, scan.summary).toEqual([]);
    await page.screenshot({
      path: test.info().outputPath(`discussion-answers-${sample.theme}.png`),
      fullPage: false,
    });
  });
}

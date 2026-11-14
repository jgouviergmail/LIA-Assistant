/**
 * The writing style LIA learned from the sent mail (ADR-383), in a real browser.
 *
 * - **What was learned is shown as text**, with how many e-mails and when, and the
 *   switch says it is on.
 * - **The switch works from the keyboard** and sends exactly the state chosen; the page
 *   shows the state the server answers.
 * - **Forgetting is asked first**: only the dialog's « Forget » sends the DELETE, and
 *   the focus comes back to the switch the section keeps.
 * - **The section passes axe and fits a 320 px phone.**
 *
 * The oracle is what is ASKED of the server and what the page says, never a class name.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
  features: { tool_approval_enabled: false, attachments_enabled: true },
  api_version: 'v1',
};

/** Mirrors `WritingStyleResponse` (domains/writing_style/schemas.py). */
function style(over: Record<string, unknown> = {}) {
  return {
    enabled: true,
    profile: 'Writes « Salut <Name> », short, signs « Seb » with « ++ » above.',
    mails_read: 12,
    learned_at: '2026-11-13T09:00:00Z',
    renews_at: '2026-12-13T09:00:00Z',
    ...over,
  };
}

interface Sent {
  patches: unknown[];
  deletes: number;
}

function routes(sent: Sent): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    {
      url: '**/api/v1/writing-style',
      handler: async route => {
        const method = route.request().method();
        if (method === 'PATCH') {
          const body = route.request().postDataJSON() as { writing_style_enabled: boolean };
          sent.patches.push(body);
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(style({ enabled: body.writing_style_enabled })),
          });
          return;
        }
        if (method === 'DELETE') {
          sent.deletes += 1;
          await route.fulfill({ status: 204, body: '' });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(style()),
        });
      },
    },
  ];
}

const SECTION = '/en/dashboard/settings?section=writing-style';

test.describe('the writing style', () => {
  test('what was learned is shown, and the switch is saved from the keyboard', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent: Sent = { patches: [], deletes: 0 };
    await authenticate({ language: 'en' });
    await mockApi(routes(sent));
    await page.goto(SECTION);

    const control = page.getByRole('switch', { name: 'Write in my voice' });
    await expect(control).toBeVisible({ timeout: 20_000 });
    await expect(control).toBeChecked();
    // Text, never markup: the angle brackets are shown as written.
    await expect(
      page.getByText('Writes « Salut <Name> », short, signs « Seb » with « ++ » above.')
    ).toBeVisible();
    await expect(page.getByText('From 12 sent e-mails', { exact: false })).toBeVisible();

    await control.focus();
    await page.keyboard.press('Space');

    await expect
      .poll(() => sent.patches, { timeout: 10_000 })
      .toEqual([{ writing_style_enabled: false }]);
    await expect(control).not.toBeChecked();
    await expect(
      page.getByText('Switched off: what was learned is kept, but not used.')
    ).toBeVisible();
    await expect(control).toBeFocused();
  });

  test('forgetting is confirmed first, and the focus returns to the switch', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent: Sent = { patches: [], deletes: 0 };
    await authenticate({ language: 'en' });
    await mockApi(routes(sent));
    await page.goto(SECTION);

    await page.getByRole('button', { name: 'Forget' }).click({ timeout: 20_000 });
    const confirm = page.getByRole('alertdialog', { name: 'Forget your writing style?' });
    await expect(confirm).toBeVisible();
    expect(sent.deletes).toBe(0);

    await confirm.getByRole('button', { name: 'Forget' }).click();

    await expect.poll(() => sent.deletes, { timeout: 10_000 }).toBe(1);
    await expect(
      page.getByText(
        'Nothing learned yet: LIA learns it the first time it writes an e-mail for you.'
      )
    ).toBeVisible();
    await expect(page.getByRole('switch', { name: 'Write in my voice' })).toBeFocused();
  });

  test('the section passes axe and fits a 320 px phone', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const sent: Sent = { patches: [], deletes: 0 };
    await authenticate({ language: 'en' });
    await mockApi(routes(sent));
    await page.goto(SECTION);
    await expect(page.getByRole('switch', { name: 'Write in my voice' })).toBeVisible({
      timeout: 20_000,
    });

    const scan = await scanPage(page, testInfo, '/dashboard/settings#writing-style');
    expect(scan.blocking, `axe violations, writing style:\n${scan.summary}`).toHaveLength(0);

    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(SECTION);
    await awaitStyledPage(page, '/dashboard/settings?section=writing-style @320px');
    await expect(page.getByRole('switch', { name: 'Write in my voice' })).toBeVisible();
    await expectNoOverflow(page, 'writing style @320px');
  });
});

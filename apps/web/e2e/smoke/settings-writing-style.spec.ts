/**
 * The writing style LIA learned from the sent mail (ADR-383), in a real browser.
 *
 * - **What was learned is shown as text**, with how many e-mails and when, and the
 *   switch says it is on.
 * - **The switch works from the keyboard** and sends exactly the state chosen; the page
 *   shows the state the server answers.
 * - **Learning happens at the person's click** (amendment 2026-11-16): one request from
 *   the keyboard, the button keeping its focus while it works, what was learned read
 *   back, and the outcome said with what it cost; with no mailbox to read, the page
 *   says so and leads to the connectors.
 * - **Forgetting is asked first**: only the dialog's « Forget » sends the DELETE, and
 *   the focus comes back to the switch the section keeps.
 * - **The section passes axe and fits a 320 px phone**, outcome notice included.
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

const PROFILE = 'Writes « Salut <Name> », short, signs « Seb » with « ++ » above.';
const NOTHING = { profile: null, mails_read: null, learned_at: null };

/** Mirrors `WritingStyleResponse` (domains/writing_style/schemas.py). */
function style(over: Record<string, unknown> = {}) {
  return {
    enabled: true,
    mails_to_read: 30,
    profile: PROFILE,
    mails_read: 12,
    learned_at: '2026-11-13T09:00:00Z',
    ...over,
  };
}

/** Mirrors `WritingStyleLearning` (domains/tool_assists/style_learning.py). */
function learned(over: Record<string, unknown> = {}) {
  return {
    outcome: 'learned',
    mails_read: 12,
    usage: { tokens_in: 900, tokens_out: 60, tokens_cache: 0, cost_eur: 0.002, model_name: 'm' },
    ...over,
  };
}

interface Sent {
  patches: unknown[];
  deletes: number;
  learnings: number;
}

interface World {
  /** What GET answers before any learning, and after one. */
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  /** What POST /learn answers. */
  learning: Record<string, unknown>;
}

function routes(sent: Sent, world?: Partial<World>): MockRoute[] {
  const before = world?.before ?? style();
  const after = world?.after ?? style();
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    {
      url: '**/api/v1/writing-style/learn',
      handler: async route => {
        sent.learnings += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(world?.learning ?? learned()),
        });
      },
    },
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
          body: JSON.stringify(sent.learnings > 0 ? after : before),
        });
      },
    },
  ];
}

function nothingSent(): Sent {
  return { patches: [], deletes: 0, learnings: 0 };
}

const SECTION = '/en/dashboard/settings?section=writing-style';

test.describe('the writing style', () => {
  test('what was learned is shown, and the switch is saved from the keyboard', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent = nothingSent();
    await authenticate({ language: 'en' });
    await mockApi(routes(sent));
    await page.goto(SECTION);

    const control = page.getByRole('switch', { name: 'Write in my voice' });
    await expect(control).toBeVisible({ timeout: 20_000 });
    await expect(control).toBeChecked();
    // Text, never markup: the angle brackets are shown as written.
    await expect(page.getByText(PROFILE)).toBeVisible();
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
    expect(sent.learnings).toBe(0);
  });

  test('a learning asked from the keyboard is said with what it learned and its cost', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent = nothingSent();
    await authenticate({ language: 'en' });
    await mockApi(routes(sent, { before: style(NOTHING), after: style() }));
    await page.goto(SECTION);

    const learn = page.getByRole('button', { name: 'Learn my style' });
    await expect(learn).toBeVisible({ timeout: 20_000 });
    await expect(
      page.getByText('Nothing learned yet: LIA learns it from your sent e-mails when you ask.')
    ).toBeVisible();

    await learn.focus();
    await page.keyboard.press('Enter');

    await expect(page.getByRole('status').getByText('Done: LIA learned how you write.')).toBeVisible(
      { timeout: 10_000 }
    );
    expect(sent.learnings).toBe(1);
    await expect(page.getByText(PROFILE)).toBeVisible();
    await expect(page.getByRole('status').getByText('Learning', { exact: false })).toBeVisible();
    // The same button, renamed in place, kept the focus through the whole act.
    await expect(page.getByRole('button', { name: 'Learn again' })).toBeFocused();
  });

  test('with no mailbox to read, the page says so and leads to the connectors', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent = nothingSent();
    await authenticate({ language: 'en' });
    await mockApi(
      routes(sent, {
        before: style(NOTHING),
        after: style(NOTHING),
        learning: learned({ outcome: 'no_mailbox', mails_read: 0, usage: null }),
      })
    );
    await page.goto(SECTION);

    await page.getByRole('button', { name: 'Learn my style' }).click({ timeout: 20_000 });

    await expect(
      page.getByText('No mailbox is connected: connect one so LIA can read your sent e-mails.')
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: 'Open Connectors' })).toHaveAttribute(
      'href',
      '/en/dashboard/settings?section=connectors'
    );
  });

  test('forgetting is confirmed first, and the focus returns to the switch', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent = nothingSent();
    await authenticate({ language: 'en' });
    await mockApi(routes(sent));
    await page.goto(SECTION);

    await page.getByRole('button', { name: 'Forget' }).click({ timeout: 20_000 });
    const confirm = page.getByRole('alertdialog', { name: 'Forget your writing style?' });
    await expect(confirm).toBeVisible();
    await expect(
      confirm.getByText('LIA deletes what it learned. Nothing is learned again until you ask.')
    ).toBeVisible();
    expect(sent.deletes).toBe(0);

    await confirm.getByRole('button', { name: 'Forget' }).click();

    await expect.poll(() => sent.deletes, { timeout: 10_000 }).toBe(1);
    await expect(
      page.getByText('Nothing learned yet: LIA learns it from your sent e-mails when you ask.')
    ).toBeVisible();
    await expect(page.getByRole('switch', { name: 'Write in my voice' })).toBeFocused();
  });

  test('the section passes axe and fits a 320 px phone, outcome notice included', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const sent = nothingSent();
    await authenticate({ language: 'en' });
    await mockApi(
      routes(sent, { learning: learned({ outcome: 'reconnect', mails_read: 0, usage: null }) })
    );
    await page.goto(SECTION);
    await page.getByRole('button', { name: 'Learn again' }).click({ timeout: 20_000 });
    await expect(page.getByRole('link', { name: 'Open Connectors' })).toBeVisible({
      timeout: 10_000,
    });

    const scan = await scanPage(page, testInfo, '/dashboard/settings#writing-style');
    expect(scan.blocking, `axe violations, writing style:\n${scan.summary}`).toHaveLength(0);

    await page.setViewportSize({ width: 320, height: 800 });
    await awaitStyledPage(page, '/dashboard/settings?section=writing-style @320px');
    await expect(page.getByRole('button', { name: 'Learn again' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Open Connectors' })).toBeVisible();
    await expectNoOverflow(page, 'writing style @320px');
  });
});

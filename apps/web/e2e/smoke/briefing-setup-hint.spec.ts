/**
 * Unconfigured briefing cards (W7) — the silence gets a name.
 *
 * `BriefingCard` renders `null` when a section is `not_configured`, and seven
 * of the nine cards reach that status without a connector. A fresh account
 * therefore landed on a home page with two empty cards and seven invisible
 * holes: nothing said a thing was missing, and nothing led to the settings.
 *
 * This is the scenario a unit test cannot cover, because the hole is precisely
 * the ABSENCE of a card: only a real render proves that the grid is quiet AND
 * that the line naming the missing cards appears next to it, pointing at the
 * settings section that actually configures each one.
 */
import { test, expect, type MockRoute } from '../fixtures';

const GENERATED_AT = '2026-07-26T08:00:00Z';

/** A section the backend reports as having no data source. */
const notConfigured = {
  status: 'not_configured',
  data: null,
  generated_at: GENERATED_AT,
  error_code: 'connector_not_configured',
  error_message: null,
};

/** A section that resolves normally but has nothing to show. */
const empty = {
  status: 'empty',
  data: null,
  generated_at: GENERATED_AT,
  error_code: null,
  error_message: null,
};

/** The shape of a brand-new account: nothing connected yet. */
const FRESH_ACCOUNT: MockRoute[] = [
  {
    url: '**/api/v1/briefing/cards',
    json: {
      cards: {
        weather: notConfigured,
        agenda: notConfigured,
        mails: notConfigured,
        birthdays: notConfigured,
        health: notConfigured,
        tasks: notConfigured,
        documents: notConfigured,
        reminders: empty,
        for_you: empty,
      },
    },
  },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: 'Bonjour', synthesis: null, generated_at: GENERATED_AT, llm_usage: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('an unconfigured dashboard says so', () => {
  test('names the missing cards instead of leaving holes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(FRESH_ACCOUNT);
    await page.goto('/fr/dashboard');

    // Addressed by ACCESSIBLE NAME: the dashboard carries other links into the
    // settings (the getting-started checklist among them), so a bare
    // `href*="section="` selector would count those too.
    const setupLinks = page.getByRole('link', { name: /Configurer la carte/ });
    await expect(setupLinks.first(), 'the missing cards must be named').toBeVisible({
      timeout: 30_000,
    });

    // Seven cards are unconfigured; each is named once and links to its own
    // settings section.
    await expect(setupLinks).toHaveCount(7);

    // The health card is gated by a toggle, not a connector: sending its owner
    // to the connectors page would be a dead end.
    await expect(setupLinks.and(page.locator('[href*="section=health-metrics"]'))).toHaveCount(1);
    await expect(setupLinks.and(page.locator('[href*="section=connectors"]'))).toHaveCount(6);
  });

  test('following a named card opens the settings section that configures it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi([
      ...FRESH_ACCOUNT,
      { url: '**/api/v1/connectors', json: { connectors: [] } },
      { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
    ]);
    await page.goto('/fr/dashboard');

    const connectorsLink = page
      .getByRole('link', { name: /Configurer la carte/ })
      .and(page.locator('[href*="section=connectors"]'))
      .first();
    await expect(connectorsLink).toBeVisible({ timeout: 30_000 });
    await connectorsLink.click();

    // The deep link must land EXPANDED — the W2 mechanism, exercised here from
    // its most valuable entry point.
    const section = page.locator('#settings-section-connectors');
    await expect(section).toBeAttached({ timeout: 30_000 });
    await expect(section).toBeVisible({ timeout: 10_000 });
  });

  test('stays quiet when everything is configured', async ({ page, authenticate, mockApi }) => {
    // The line must not become permanent furniture: a configured account sees
    // nothing at all.
    const ok = { ...empty, status: 'empty' };
    await authenticate({ language: 'fr' });
    await mockApi([
      {
        url: '**/api/v1/briefing/cards',
        json: {
          cards: {
            weather: ok,
            agenda: ok,
            mails: ok,
            birthdays: ok,
            health: ok,
            tasks: ok,
            documents: ok,
            reminders: ok,
            for_you: ok,
          },
        },
      },
      ...FRESH_ACCOUNT.slice(1),
    ]);
    await page.goto('/fr/dashboard');

    // Anchor on the grid's own heading — the dashboard has no h1.
    await expect(page.getByRole('heading', { name: /Mon dashboard/ })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole('link', { name: /Configurer la carte/ })).toHaveCount(0);
  });
});

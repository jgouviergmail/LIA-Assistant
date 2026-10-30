/**
 * The progressive dashboard (spec 2026-10-21 §5.8, D3) in a real browser.
 *
 * Hermetic: the initial read answers at once with the reminders card and the
 * weather PENDING; the weather's own section read is held until the test lets
 * it go; the text is a POST that must wait for every section to settle. Proves:
 *   - the reminders card is readable while the weather tile is still loading,
 *     and the page announces its loading ONCE;
 *   - nothing names the pending weather as a missing source;
 *   - the text is asked for only after the weather settled, with the act.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, briefingWindowsMock, type MockRoute } from '../fixtures';

const AT = '2026-10-28T08:00:00Z';
const ACT = 'e2e-progressive-act';

function card(status: string, data: unknown = null) {
  return {
    status,
    data,
    generated_at: AT,
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const empty = card('empty');
const REMINDERS = card('ok', {
  items: [{ id: 'r1', content: 'Appeler la boulangerie', trigger_at_local: '18:00' }],
});
const WEATHER = card('ok', {
  temperature_c: 14,
  temperature_min_c: 9,
  temperature_max_c: 17,
  condition_code: 'CLEAR',
  description: 'Ciel dégagé',
  icon_emoji: '☀️',
  location_city: 'Lyon',
  wind_speed_kmh: 8,
  wind_direction_cardinal: 'N',
  precipitation_probability: 0.1,
  forecast_alert: null,
  daily_forecast: [],
  air_quality: null,
  pollen: [],
});

function routes(release: Promise<void>, textBodies: unknown[]): MockRoute[] {
  return [
    {
      url: '**/api/v1/briefing/cards/initial',
      json: {
        windows: briefingWindowsMock,
        cards: {
          weather: card('pending'),
          agenda: empty,
          mails: empty,
          birthdays: empty,
          reminders: REMINDERS,
          health: empty,
          for_you: empty,
          tasks: empty,
          documents: empty,
          workboard: empty,
        },
        pending: ['weather'],
        act: ACT,
        act_expires_at: '2099-01-01T00:00:00Z',
        section_concurrency: 4,
      },
    },
    {
      url: /\/api\/v1\/briefing\/sections\/weather(?:\?.*)?$/,
      handler: async route => {
        await release;
        await route.fulfill({ json: WEATHER });
      },
    },
    {
      url: '**/api/v1/briefing/text',
      method: 'POST',
      handler: async route => {
        textBodies.push(route.request().postDataJSON());
        await route.fulfill({
          json: {
            greeting: { text: 'Bonjour, belle journée en vue.', generated_at: AT, usage: null },
            synthesis: null,
            reused: false,
            state: 'ready',
          },
        });
      },
    },
    { url: '**/api/v1/usage/**', json: {} },
  ];
}

test.describe('the progressive dashboard', () => {
  test('shows a local card while a slow section loads, then asks for the text once', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const weatherHeld = new Promise<void>(resolve => {
      release = resolve;
    });
    const textBodies: unknown[] = [];
    await authenticate({ language: 'fr' });
    await mockApi(routes(weatherHeld, textBodies));
    await page.goto('/fr/dashboard');

    await expect(page.getByText('Appeler la boulangerie')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('briefing-card-skeleton')).toHaveCount(1);
    await expect(page.getByRole('status').filter({ hasText: 'Chargement...' })).toHaveCount(1);
    await expect(page.getByRole('link', { name: /Configurer la carte/ })).toHaveCount(0);
    expect(textBodies).toEqual([]);

    release();

    await expect(page.getByRole('region', { name: 'Météo' })).toBeVisible();
    await expect(page.getByTestId('briefing-card-skeleton')).toHaveCount(0);
    await expect.poll(() => textBodies).toEqual([{ act: ACT, force: false }]);
  });
});

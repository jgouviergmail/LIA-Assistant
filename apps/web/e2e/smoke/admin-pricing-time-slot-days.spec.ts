/**
 * Admin screen smoke — the days of a pricing window (ADR-223 amendment).
 *
 * DeepSeek bills its peak windows Monday to Friday; a window now carries the
 * UTC days it applies on. The component suite proves the form's logic in
 * jsdom; this proves what jsdom cannot: that in a REAL browser the stored days
 * come back pressed, a key press toggles one, and the seven toggles of a window
 * fit a phone without a horizontal scroll.
 *
 * Hermetic: /auth/me returns a superuser, the model list and its reasoning
 * family are mocked, every other API call dies on the 501 catch-all. The save
 * itself goes through a server action — outside the browser, so outside this
 * harness; its payload is pinned by the component and helper suites.
 */
import { test, expect, type MockRoute } from '../fixtures';

const WEEKDAY_WINDOW = {
  input_unit_price: '0.300000',
  cached_input_unit_price: '0.006000',
  output_unit_price: '1.200000',
  weekdays: [1, 2, 3, 4, 5],
};

const model = {
  id: '3f1d9b2a-0000-4000-8000-000000000023',
  provider: 'deepseek',
  model_name: 'deepseek-flash',
  max_input_tokens: 1000000,
  max_output_tokens: 384000,
  supports_tools: true,
  supports_structured_output: true,
  supports_strict_mode: false,
  supports_streaming: true,
  supports_vision: true,
  is_reasoning_model: true,
  kind: 'chat',
  reasoning_enum_values: ['none', 'low', 'high', 'max'],
  reasoning_doc_i18n_key: 'deepseek_v4',
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  pricing_unit: 'per_1m_tokens',
  input_unit_price: '0.150000',
  cached_input_unit_price: '0.003000',
  output_unit_price: '0.600000',
  time_slots: [
    { start_utc: '01:00', end_utc: '04:00', ...WEEKDAY_WINDOW },
    { start_utc: '06:00', end_utc: '10:00', ...WEEKDAY_WINDOW },
  ],
  effective_from: '2026-09-11T22:42:59Z',
  is_active: true,
};

const routes: MockRoute[] = [
  {
    url: '**/api/v1/admin/llm/pricing?*',
    method: 'GET',
    json: { total: 1, page: 1, page_size: 20, total_pages: 1, models: [model] },
  },
  {
    url: '**/api/v1/admin/llm/reasoning-family*',
    method: 'GET',
    json: {
      reasoning_family: 'deepseek_v4',
      reasoning_levels: ['none', 'low', 'high', 'max'],
      reasoning_can_disable: true,
      reasoning_supports_budget: false,
      reasoning_budget_range: null,
      source: 'family',
    },
  },
];

const DAYS_LABEL = 'Days it applies (the UTC day the window starts)';

async function openTheWindowedModel(
  page: import('@playwright/test').Page
): Promise<import('@playwright/test').Locator> {
  await page.goto('/en/dashboard/settings?section=admin-llm-pricing');
  await expect(page.getByRole('cell', { name: 'deepseek-flash' })).toBeVisible();
  await page.getByRole('button', { name: 'Edit' }).first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe('admin pricing window days (superuser)', () => {
  test('the stored days come back pressed, and a key press toggles one', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ is_superuser: true });
    await mockApi(routes);
    const dialog = await openTheWindowedModel(page);

    const firstWindow = dialog.getByRole('group', { name: DAYS_LABEL }).first();
    await expect(firstWindow.getByRole('button', { name: 'Mon' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    const saturday = firstWindow.getByRole('button', { name: 'Sat' });
    await expect(saturday).toHaveAttribute('aria-pressed', 'false');

    await saturday.focus();
    await page.keyboard.press('Space');

    await expect(saturday).toHaveAttribute('aria-pressed', 'true');
    await expect(saturday).toBeFocused();
  });

  test('the seven days of a window fit a phone without a horizontal scroll', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ is_superuser: true });
    await mockApi(routes);
    // Opened at the desktop width, where the row's Edit button is inline (a
    // phone folds row actions into a menu), then narrowed: the dialog reflows.
    const dialog = await openTheWindowedModel(page);
    await page.setViewportSize({ width: 390, height: 844 });

    const firstWindow = dialog.getByRole('group', { name: DAYS_LABEL }).first();
    await firstWindow.scrollIntoViewIfNeeded();
    for (const day of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
      await expect(firstWindow.getByRole('button', { name: day })).toBeInViewport();
    }
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({
      path: test.info().outputPath('pricing-window-days-390.png'),
      fullPage: false,
    });
  });
});

/**
 * Admin screen smoke — the pricing workbook round trip (ADR-228).
 *
 * The component suite proves the dialog's logic in jsdom; this proves the two
 * things jsdom cannot: that a REAL file chosen in a REAL browser reaches the
 * API as multipart (the client forces `application/json`, which is why this
 * one call bypasses it), and that the apply request carries the fingerprint of
 * the plan the administrator actually read.
 *
 * Hermetic: /auth/me returns a superuser, the model list and both import calls
 * are mocked, every other API call dies on the 501 catch-all. The dry run and
 * the apply are served by ONE handler that asserts on the query string, so a
 * regression that applies without reviewing shows up as a missing preview
 * rather than as a silent write.
 */
import { test, expect, type MockRoute } from '../fixtures';

const model = {
  id: '3f1d9b2a-0000-4000-8000-000000000011',
  provider: 'openai',
  model_name: 'gpt-4.1-mini',
  max_input_tokens: 1047576,
  max_output_tokens: 32768,
  supports_tools: true,
  supports_structured_output: true,
  supports_strict_mode: true,
  supports_streaming: true,
  supports_vision: true,
  is_reasoning_model: false,
  kind: 'chat',
  reasoning_widget: 'none',
  reasoning_enum_values: null,
  reasoning_budget_range: null,
  reasoning_doc_i18n_key: null,
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  pricing_unit: 'per_1m_tokens',
  input_unit_price: '0.400000',
  cached_input_unit_price: '0.100000',
  output_unit_price: '1.600000',
  time_slots: null,
  effective_from: '2026-01-01T00:00:00Z',
  is_active: true,
};

const PLAN_FINGERPRINT = 'e3b0c44298fc1c14';

const plan = {
  plan_fingerprint: PLAN_FINGERPRINT,
  counts: { update: 1, unchanged: 123 },
  changes: [
    {
      model_name: 'gpt-4.1-mini',
      action: 'update',
      fields: [{ field: 'input_unit_price', before: '0.400000', after: '0.500000' }],
      slots_before: 0,
      slots_after: 0,
      row_number: 12,
    },
  ],
  issues: [],
  is_applicable: true,
  pricing_changes: ['gpt-4.1-mini'],
};

/** Every request the import endpoint received, in order — the oracle. */
interface ImportCall {
  readonly dryRun: string | null;
  readonly fingerprint: string | null;
  readonly contentType: string;
  readonly hasFileName: boolean;
}

test.describe('admin pricing workbook (superuser)', () => {
  test('previews the edited workbook, then applies exactly the reviewed plan', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const calls: ImportCall[] = [];

    const routes: MockRoute[] = [
      {
        url: '**/api/v1/admin/llm/pricing?*',
        method: 'GET',
        json: { total: 1, page: 1, page_size: 20, total_pages: 1, models: [model] },
      },
      {
        url: '**/api/v1/admin/llm/pricing/sheet/import*',
        method: 'POST',
        handler: async route => {
          const url = new URL(route.request().url());
          const body = route.request().postData() ?? '';
          calls.push({
            dryRun: url.searchParams.get('dry_run'),
            fingerprint: url.searchParams.get('plan_fingerprint'),
            contentType: route.request().headers()['content-type'] ?? '',
            // A multipart body names the field and the file it carries.
            hasFileName: body.includes('filename="tarifs.xlsx"'),
          });
          const applied = url.searchParams.get('dry_run') === 'false';
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              applied,
              plan,
              created: [],
              updated: applied ? ['gpt-4.1-mini'] : [],
              deactivated: [],
              reactivated: [],
              unchanged: 123,
            }),
          });
        },
      },
    ];

    await authenticate({ is_superuser: true });
    await mockApi(routes);

    await page.goto('/en/dashboard/settings?section=admin-llm-pricing');
    await expect(page.getByRole('cell', { name: 'gpt-4.1-mini' })).toBeVisible();

    // At the default desktop viewport `SectionToolbar` renders its foldable
    // actions as plain buttons; the "..." menu is `sm:hidden`.
    await page.getByRole('button', { name: 'Import workbook' }).click();

    const dialog = page.getByRole('dialog', { name: 'Import a pricing workbook' });
    await expect(dialog).toBeVisible();

    // Nothing can be applied before a plan has been reviewed.
    await expect(dialog.getByRole('button', { name: 'Apply these changes' })).toHaveCount(0);

    // A real file, chosen through the real (hidden) native input.
    await page.getByTestId('pricing-sheet-file-input').setInputFiles({
      name: 'tarifs.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('PK not a real workbook, the server is mocked'),
    });

    // The preview names the model and shows the price move, before and after.
    await expect(dialog.getByText('gpt-4.1-mini')).toBeVisible();
    await expect(dialog.getByText('0.400000')).toBeVisible();
    await expect(dialog.getByText('0.500000')).toBeVisible();
    await expect(dialog.getByText(/123.*unchanged|unchanged.*123/i)).toBeVisible();

    const apply = dialog.getByRole('button', { name: 'Apply these changes' });
    await expect(apply).toBeVisible();
    await apply.click();

    await expect(dialog.getByText('Changes applied')).toBeVisible();

    // Two calls: a dry run that wrote nothing, then an apply carrying the
    // fingerprint of the very plan that was rendered above.
    expect(calls).toHaveLength(2);
    expect(calls[0].dryRun).toBe('true');
    expect(calls[0].fingerprint).toBeNull();
    expect(calls[1].dryRun).toBe('false');
    expect(calls[1].fingerprint).toBe(PLAN_FINGERPRINT);

    // The file really travelled as multipart, with a browser-set boundary.
    for (const call of calls) {
      expect(call.contentType).toContain('multipart/form-data');
      expect(call.contentType).toContain('boundary=');
      expect(call.hasFileName).toBe(true);
    }
  });
});

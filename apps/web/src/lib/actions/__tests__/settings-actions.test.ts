/**
 * Admin Server Actions — user lifecycle and the three pricing catalogues.
 *
 * These actions never throw: they return `{success, message | error}` and the
 * admin UI renders whichever came back. That makes the **error** branch the
 * risky one — it is what an admin reads when a deactivation is refused or a
 * model name collides — and it was the branch that silently lost the backend's
 * reason (the axios-shaped `err.response.data.detail` read, against a client
 * that has always thrown `.data`).
 *
 * The API client is driven for real over a stubbed `next/headers` + `fetch`, so
 * a change to the error envelope surfaces here.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { cookieGet } = vi.hoisted(() => ({ cookieGet: vi.fn() }));
vi.mock('next/headers', () => ({ cookies: async () => ({ get: cookieGet }) }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import {
  toggleUserActive,
  deleteUserAccount,
  deleteUserGDPR,
  createLLMPricing,
  updateLLMPricing,
  fetchReasoningTemplates,
  reloadLLMPricingCache,
  deactivateLLMPricing,
  createGoogleApiPricing,
  updateGoogleApiPricing,
  deactivateGoogleApiPricing,
  reloadGoogleApiPricingCache,
  createImagePricing,
  updateImagePricing,
  deactivateImagePricing,
  reloadImagePricingCache,
} from '@/lib/actions/settings-actions';

/** The creation payload, read off the action's own signature. */
type LLMPricingData = Parameters<typeof createLLMPricing>[0];

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** Make every request answer with this status/body. */
function respond(status: number, body: unknown): void {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(async () =>
    jsonResponse(status, body)
  );
}

function lastRequest(): { url: string; init: RequestInit } {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const call = mock.mock.calls.at(-1)!;
  return { url: call[0] as string, init: call[1] as RequestInit };
}

const ORIGINAL_FETCH = globalThis.fetch;

const PRICING: LLMPricingData = {
  provider: 'openai',
  model_name: 'gpt-x',
  max_input_tokens: 100,
  max_output_tokens: 100,
  supports_tools: true,
  supports_structured_output: true,
  supports_strict_mode: false,
  supports_streaming: true,
  supports_vision: false,
  input_unit_price: '1.00',
  cached_input_unit_price: null,
  output_unit_price: '2.00',
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  cookieGet.mockReturnValue({ name: 'lia_session', value: 'sess-42' });
  process.env.API_URL_SERVER = 'http://api:8000';
  globalThis.fetch = vi.fn().mockImplementation(async () => jsonResponse(200, {}));
});

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = ORIGINAL_FETCH;
});

describe('toggleUserActive', () => {
  it('patches the activation endpoint and confirms', async () => {
    respond(200, {
      user: {},
      email_notification_sent: false,
      email_notification_error: null,
    });

    const result = await toggleUserActive('u1', true);

    const { url, init } = lastRequest();
    expect(url).toBe('http://api:8000/api/v1/users/admin/u1/activation');
    expect(init.method).toBe('PATCH');
    expect(init.body).toBe('{"is_active":true}');
    expect(result.success).toBe(true);
    expect(result.message).toContain('activé');
  });

  it('carries the deactivation reason only when deactivating', async () => {
    respond(200, { user: {}, email_notification_sent: false, email_notification_error: null });

    await toggleUserActive('u1', false, 'abuse');
    expect(lastRequest().init.body).toBe('{"is_active":false,"reason":"abuse"}');

    await toggleUserActive('u1', true, 'abuse');
    expect(lastRequest().init.body).toBe('{"is_active":true}');
  });

  it('reports that the notification email went out', async () => {
    respond(200, { user: {}, email_notification_sent: true, email_notification_error: null });

    const result = await toggleUserActive('u1', false);
    expect(result.message).toContain('email de notification a été envoyé');
  });

  it('warns when the operation succeeded but the email failed', async () => {
    respond(200, {
      user: {},
      email_notification_sent: false,
      email_notification_error: 'SMTP unreachable',
    });

    const result = await toggleUserActive('u1', false);
    expect(result.success).toBe(true);
    expect(result.message).toContain('SMTP unreachable');
  });

  it("hands back the backend's own refusal instead of a generic sentence", async () => {
    respond(409, { detail: 'User is the last superuser' });

    const result = await toggleUserActive('u1', false);
    expect(result).toEqual({ success: false, error: 'User is the last superuser' });
  });

  it('falls back to the generic wording when the failure says nothing', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new TypeError('fetch failed'));

    const result = await toggleUserActive('u1', false);
    expect(result.success).toBe(false);
    expect(result.error).toBe("Erreur lors de la désactivation de l'utilisateur");
  });
});

describe('user deletion lifecycle', () => {
  it('soft-deletes with the reason in the body', async () => {
    await deleteUserAccount('u1', 'gdpr request');

    const { url, init } = lastRequest();
    expect(url).toBe('http://api:8000/api/v1/users/admin/u1/delete-account');
    expect(init.method).toBe('DELETE');
    expect(init.body).toBe('{"reason":"gdpr request"}');
  });

  it('soft-deletes without a body when no reason is given', async () => {
    await deleteUserAccount('u1');
    expect(lastRequest().init.body).toBeUndefined();
  });

  it('surfaces the precondition the backend enforces', async () => {
    respond(409, { detail: 'User must be deactivated first' });

    await expect(deleteUserAccount('u1')).resolves.toEqual({
      success: false,
      error: 'User must be deactivated first',
    });
  });

  it('hard-deletes through the GDPR endpoint', async () => {
    const result = await deleteUserGDPR('u1');

    expect(lastRequest().url).toBe('http://api:8000/api/v1/users/admin/u1/gdpr');
    expect(result.success).toBe(true);
  });

  it('surfaces the GDPR precondition', async () => {
    respond(409, { detail: 'User must be soft-deleted first' });

    await expect(deleteUserGDPR('u1')).resolves.toEqual({
      success: false,
      error: 'User must be soft-deleted first',
    });
  });
});

describe('LLM pricing catalogue', () => {
  it('creates a model and names it back', async () => {
    const result = await createLLMPricing(PRICING);

    const { url, init } = lastRequest();
    expect(url).toBe('http://api:8000/api/v1/admin/llm/pricing');
    expect(init.method).toBe('POST');
    expect(result.message).toContain('gpt-x');
  });

  it('surfaces a duplicate-model conflict verbatim', async () => {
    respond(409, { detail: 'Pricing for gpt-x already exists' });

    await expect(createLLMPricing(PRICING)).resolves.toEqual({
      success: false,
      error: 'Pricing for gpt-x already exists',
    });
  });

  it('updates under the ORIGINAL name and reports the new one', async () => {
    const result = await updateLLMPricing('gpt-old', { model_name: 'gpt-new' });

    expect(lastRequest().url).toBe('http://api:8000/api/v1/admin/llm/pricing/gpt-old');
    expect(result.message).toContain('gpt-new');
  });

  it('keeps the original name in the message when the rename field is absent', async () => {
    const result = await updateLLMPricing('gpt-old', { max_input_tokens: 42 });
    expect(result.message).toContain('gpt-old');
  });

  it('joins a structured 422 into one readable error', async () => {
    respond(422, {
      detail: [
        { loc: ['body', 'max_output_tokens'], msg: 'must be greater than 0' },
        { loc: ['body', 'input_unit_price'], msg: 'must be a decimal string' },
      ],
    });

    await expect(updateLLMPricing('gpt-old', {})).resolves.toEqual({
      success: false,
      error: 'must be greater than 0, must be a decimal string',
    });
  });

  it('returns the reasoning templates list', async () => {
    respond(200, { templates: [{ template_model_name: 'o3' }] });

    await expect(fetchReasoningTemplates()).resolves.toEqual([{ template_model_name: 'o3' }]);
  });

  it('lets a template fetch failure propagate — it has no ActionResponse to fill', async () => {
    respond(503, { detail: 'db down' });

    await expect(fetchReasoningTemplates()).rejects.toMatchObject({ status: 503 });
  });

  it('reloads and deactivates through their own endpoints', async () => {
    await reloadLLMPricingCache();
    expect(lastRequest().url).toBe('http://api:8000/api/v1/admin/llm/pricing/reload-cache');

    await deactivateLLMPricing('p1');
    expect(lastRequest()).toMatchObject({
      url: 'http://api:8000/api/v1/admin/llm/pricing/p1',
      init: { method: 'DELETE' },
    });
  });

  it.each([
    ['reload', () => reloadLLMPricingCache(), 'Erreur lors du rechargement du cache'],
    ['deactivate', () => deactivateLLMPricing('p1'), 'Erreur lors de la désactivation'],
  ])('%s falls back to its own generic wording', async (_label, run, expected) => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new TypeError('fetch failed'));
    await expect(run()).resolves.toEqual({ success: false, error: expected });
  });
});

describe('Google API pricing catalogue', () => {
  const entry = {
    api_name: 'places',
    endpoint: '/v1/places:searchText',
    sku_name: 'Text Search',
    cost_per_1000_usd: '32.00',
  };

  it('creates an entry and names it back', async () => {
    const result = await createGoogleApiPricing(entry);

    expect(lastRequest().url).toBe('http://api:8000/api/v1/admin/google-api/pricing');
    expect(result.message).toContain('places:/v1/places:searchText');
  });

  it('URL-encodes the endpoint segment on update', async () => {
    await updateGoogleApiPricing('places', '/v1/places:searchText', {
      sku_name: 'Text Search',
      cost_per_1000_usd: '35.00',
    });

    expect(lastRequest().url).toBe(
      'http://api:8000/api/v1/admin/google-api/pricing/places/%2Fv1%2Fplaces%3AsearchText'
    );
  });

  it('reports the renamed pair when the payload renames it', async () => {
    const result = await updateGoogleApiPricing('places', '/old', {
      api_name: 'routes',
      endpoint: '/new',
      sku_name: 's',
      cost_per_1000_usd: '1',
    });

    expect(result.message).toContain('routes:/new');
  });

  it('surfaces the backend refusal on update', async () => {
    respond(422, { detail: 'cost_per_1000_usd must be positive' });

    await expect(
      updateGoogleApiPricing('places', '/v1', { sku_name: 's', cost_per_1000_usd: '-1' })
    ).resolves.toEqual({ success: false, error: 'cost_per_1000_usd must be positive' });
  });

  it('deactivates and reloads through their own endpoints', async () => {
    await deactivateGoogleApiPricing('gp1');
    expect(lastRequest().url).toBe('http://api:8000/api/v1/admin/google-api/pricing/gp1');

    await reloadGoogleApiPricingCache();
    expect(lastRequest().url).toBe('http://api:8000/api/v1/admin/google-api/pricing/reload-cache');
  });

  it('falls back to the generic creation wording', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new TypeError('fetch failed'));

    await expect(createGoogleApiPricing(entry)).resolves.toEqual({
      success: false,
      error: 'Erreur lors de la création du tarif',
    });
  });
});

describe('image generation pricing catalogue', () => {
  const entry = {
    provider: 'openai' as const,
    model: 'gpt-image-1',
    quality: 'high',
    size: '1024x1024',
    cost_per_image_usd: '0.19',
  };

  it('creates an entry and describes it', async () => {
    const result = await createImagePricing(entry);

    expect(lastRequest().url).toBe('http://api:8000/api/v1/admin/image-pricing/pricing');
    expect(result.message).toBe('Pricing gpt-image-1/high/1024x1024 created.');
  });

  it('updates by id and confirms a new version', async () => {
    const result = await updateImagePricing('ip1', { cost_per_image_usd: '0.21' });

    expect(lastRequest()).toMatchObject({
      url: 'http://api:8000/api/v1/admin/image-pricing/pricing/ip1',
      init: { method: 'PUT' },
    });
    expect(result.message).toContain('New version created');
  });

  it('deactivates and reloads', async () => {
    await deactivateImagePricing('ip1');
    expect(lastRequest().init.method).toBe('DELETE');

    await reloadImagePricingCache();
    expect(lastRequest().url).toBe(
      'http://api:8000/api/v1/admin/image-pricing/pricing/reload-cache'
    );
  });

  it.each([
    ['create', () => createImagePricing(entry), 'Error creating image pricing'],
    [
      'update',
      () => updateImagePricing('ip1', { cost_per_image_usd: '1' }),
      'Error updating image pricing',
    ],
    ['deactivate', () => deactivateImagePricing('ip1'), 'Error deactivating image pricing'],
    ['reload', () => reloadImagePricingCache(), 'Error reloading cache'],
  ])('%s falls back to its own generic wording', async (_label, run, expected) => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new TypeError('fetch failed'));
    await expect(run()).resolves.toEqual({ success: false, error: expected });
  });

  it("surfaces the backend's reason on a refused image pricing", async () => {
    respond(409, { detail: 'This model/quality/size triplet already has a price' });

    await expect(createImagePricing(entry)).resolves.toEqual({
      success: false,
      error: 'This model/quality/size triplet already has a price',
    });
  });
});

describe('every admin action authenticates', () => {
  it('forwards the session cookie on a mutation', async () => {
    await deactivateLLMPricing('p1');

    const headers = lastRequest().init.headers as Record<string, string>;
    expect(headers.Cookie).toBe('lia_session=sess-42');
  });
});

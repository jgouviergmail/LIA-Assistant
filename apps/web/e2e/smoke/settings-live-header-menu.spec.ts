/**
 * The header's voice menu follows the Live settings (owner request 2026-09-19).
 *
 * The voice toggle sits in the dashboard layout and never remounts on the way
 * between the settings and the chat: it read the live connectors ONCE, so a
 * provider or model changed in the Live settings kept the old brand on
 * « Session Live (<brand>) » until a reload. The settings now declare the
 * change (`live_connectors` revision) and the menu re-reads.
 *
 * Journey, on ONE page (the exact stale case): the menu names Gemini → the
 * Live settings switch the model to an ElevenLabs agent and save → the menu
 * names ElevenLabs, and the direct entry follows the chosen model's
 * capability (an agent's wire carries no tool schema: no direct entry).
 */
import { test, expect, type MockRoute } from '../fixtures';

const CAPABILITIES = {
  async_delegation: true,
  delivery_scheduling: true,
  reports_idle: false,
  cancels_on_interruption: true,
  configurable_vad: true,
  resumes: true,
  thinking: false,
  direct_tools: true,
  portal_voice: false,
};
const AGENT_CAPABILITIES = { ...CAPABILITIES, direct_tools: false, portal_voice: true };

const SETTINGS = {
  model: 'gemini-x-live',
  voice: 'Kore',
  thinking_level: null,
  session_budget_eur: null,
  idle_timeout_seconds: 300,
  session_max_minutes: 30,
};

function connectors(activeProvider: 'gemini' | 'elevenlabs') {
  return {
    active_provider: activeProvider,
    connectors: [
      {
        provider: 'gemini',
        connector_type: 'gemini_live',
        status: 'active',
        settings: SETTINGS,
        model_settings: {},
        functionally_verified: true,
        capabilities: CAPABILITIES,
        active: activeProvider === 'gemini',
      },
      {
        provider: 'elevenlabs',
        connector_type: 'elevenlabs_live',
        status: 'active',
        settings: { ...SETTINGS, model: 'agent_1', voice: 'agent' },
        model_settings: {},
        functionally_verified: true,
        capabilities: AGENT_CAPABILITIES,
        active: activeProvider === 'elevenlabs',
      },
    ],
  };
}

function routes(state: { active: 'gemini' | 'elevenlabs' }, saves: unknown[]): MockRoute[] {
  return [
    {
      url: '**/api/v1/config',
      json: {
        sse: { heartbeat_interval_seconds: 15 },
        rate_limits: { enabled: false, per_minute: 60, burst: 10 },
        i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
        features: { live_enabled: true },
        api_version: 'v1',
      },
    },
    { url: '**/api/v1/connectors', json: { connectors: [] } },
    {
      url: '**/api/v1/live/connectors',
      method: 'GET',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(connectors(state.active)),
        });
      },
    },
    {
      url: '**/api/v1/live/connectors/elevenlabs',
      method: 'PUT',
      handler: async route => {
        saves.push(route.request().postDataJSON());
        state.active = 'elevenlabs';
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(connectors('elevenlabs').connectors[1]),
        });
      },
    },
    {
      url: '**/api/v1/live/models',
      json: {
        models: [
          {
            provider: 'gemini',
            name: 'gemini-x-live',
            thinking_levels: [],
            capabilities: CAPABILITIES,
          },
          {
            provider: 'elevenlabs',
            name: 'agent_1',
            label: 'Concierge',
            thinking_levels: [],
            capabilities: AGENT_CAPABILITIES,
          },
        ],
        default_model: 'gemini-x-live',
        unpriced: [],
      },
    },
    {
      url: '**/api/v1/live/voices?provider=*',
      json: {
        provider: 'gemini',
        voices: [{ name: 'Kore', characteristic: 'Firm' }],
        provenance: 'published',
        published_at: null,
        source: null,
      },
    },
    {
      url: '**/api/v1/live/config',
      json: {
        session_max_minutes: 30,
        connect_window_seconds: 60,
        idle_timeout_seconds: 300,
        hidden_grace_seconds: 20,
        delegation_timeout_seconds: 90,
        delegation_result_max_tokens: 600,
        delegation_tool_name: 'send_to_lia',
        turn_text_max_chars: 4000,
        delegation_lines: { timed_out: 'T', result_cut: 'C', superseded: 'X', empty_request: 'E' },
        direct_lines: { lookup_failed: 'F' },
        session_max_bounds: { min: 1, max: 240 },
        idle_timeout_bounds: { min: 5, max: 3600 },
        unlimited_value: 0,
        tone_lines: {},
      },
    },
  ];
}

test.describe('settings — the header voice menu follows the Live settings', () => {
  test('a provider saved in the Live settings renames the menu entries without a reload', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const state = { active: 'gemini' as 'gemini' | 'elevenlabs' };
    const saves: unknown[] = [];
    await mockApi(routes(state, saves));
    await page.goto('/fr/dashboard/settings?section=live-mode');
    await expect(page.locator('#settings-section-live-mode')).toBeVisible({ timeout: 20_000 });

    // Before: the menu names Gemini, whose model can hold a direct session.
    const menuButton = page.getByRole('button', { name: 'Voix et session live' });
    await menuButton.click();
    const items = page.getByRole('menuitem');
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toHaveText(/Session Live \(Gemini\)/);
    await expect(items.nth(1)).toHaveText(/Session Live directe \(Gemini\)/);
    await page.keyboard.press('Escape');
    await expect(items).toHaveCount(0);

    // The Live settings: switch the model to the ElevenLabs agent and save.
    await page.getByRole('combobox', { name: 'Modèle' }).click();
    await page.getByRole('option', { name: 'Concierge' }).click();
    await page.getByRole('button', { name: 'Enregistrer le connecteur' }).click();
    await expect.poll(() => saves.length).toBe(1);
    await expect(page.getByText('Connecteur Live mis à jour.')).toBeVisible();

    // After, on the same layout mount: the menu names ElevenLabs, and offers no
    // direct entry — an agent's wire carries no tool schema.
    await menuButton.click();
    await expect(items).toHaveCount(1);
    await expect(items.nth(0)).toHaveText(/Session Live \(ElevenLabs\)/);
  });
});

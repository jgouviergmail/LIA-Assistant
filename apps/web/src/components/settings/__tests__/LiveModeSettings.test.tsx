/**
 * LiveModeSettings — nothing without the instance flag; a link to the
 * connectors without a connector; with one, the three choices save through
 * one PUT on the provider's own route (a refusal in an alert, in the server's
 * words). The category is additive (wave 2 A10): the model list is the UNION
 * of every active key's models grouped by provider, choosing another
 * provider's model lists ITS voices and saves under it, and the reflexes a
 * provider cannot honour are not offered. Each of the four reflexes saves the
 * WHOLE preferences object at once.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';

const CAPABILITIES = {
  async_delegation: true,
  delivery_scheduling: true,
  reports_idle: false,
  cancels_on_interruption: true,
  configurable_vad: true,
  resumes: true,
  thinking: false,
};

const h = vi.hoisted(() => ({
  liveEnabled: true,
  connectors: null as unknown,
  models: null as unknown,
  put: vi.fn(),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { live_enabled: h.liveEnabled } } }),
}));
const sample = vi.hoisted(() => ({ play: vi.fn(async () => {}), playing: false }));
vi.mock('@/hooks/useVoiceSample', () => ({ useVoiceSample: () => sample }));

const MODELS = {
  models: [
    { provider: 'gemini', name: 'gemini-x-live', thinking_levels: [], capabilities: CAPABILITIES },
    {
      provider: 'gemini',
      name: 'gemini-x-live-extended-thinking',
      thinking_levels: ['low', 'high'],
      capabilities: CAPABILITIES,
    },
    {
      provider: 'openai',
      name: 'gpt-x-live',
      thinking_levels: [],
      capabilities: { ...CAPABILITIES, configurable_vad: false },
    },
    {
      provider: 'elevenlabs',
      name: 'agent_0123456789abcdef',
      label: 'Assistant',
      thinking_levels: [],
      capabilities: { ...CAPABILITIES, configurable_vad: false, portal_voice: true, vendor_billed: true },
    },
  ],
  default_model: 'gemini-x-live',
  unpriced: [],
};
const PORTAL_VOICES = { provider: 'elevenlabs', voices: [], provenance: 'portal' };
const GEMINI_VOICES = {
  provider: 'gemini',
  voices: [
    { name: 'Kore', characteristic: 'Firm' },
    { name: 'Puck', characteristic: 'Upbeat' },
  ],
  provenance: 'published',
  published_at: '2026-09-18',
  source: null,
};
const OPENAI_VOICES = {
  provider: 'openai',
  voices: [{ name: 'Marin', characteristic: 'Warm' }],
  provenance: 'published',
  published_at: '2026-09-18',
  source: null,
};
const PREFS = {
  interruptions: true,
  end_of_speech: 'normal',
  result_delivery: 'interrupt',
};
const LIVE_CONFIG = {
  session_max_minutes: 10,
  extension_minutes: 10,
  extension_prompt_seconds: 60,
  connect_window_seconds: 60,
  idle_timeout_seconds: 60,
  hidden_grace_seconds: 20,
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  delegation_tool_name: 'send_to_lia',
  turn_text_max_chars: 4000,
  delegation_lines: { timed_out: 'T', result_cut: 'C', superseded: 'X', empty_request: 'E' },
  session_max_bounds: { min: 1, max: 240 },
  idle_timeout_bounds: { min: 5, max: 3600 },
  unlimited_value: 0,
  session_budget_eur_max: 100,
};
const DURATIONS = { idle_timeout_seconds: 60, session_max_minutes: 10 };

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (url: string, options: { enabled: boolean }) => {
    const table: Record<string, unknown> = {
      '/live/connectors': h.connectors,
      '/live/models': h.models,
      '/live/voices?provider=gemini': GEMINI_VOICES,
      '/live/voices?provider=openai': OPENAI_VOICES,
      '/live/voices?provider=elevenlabs': PORTAL_VOICES,
      '/live/preferences': PREFS,
      '/live/config': LIVE_CONFIG,
    };
    return {
      data: options.enabled ? table[url] : undefined,
      loading: false,
      error: null,
      refetch: vi.fn(),
      setData: vi.fn(),
    };
  },
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({
    mutate: h.put,
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
  }),
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { LiveModeSettings } from '../LiveModeSettings';

const GEMINI = {
  provider: 'gemini',
  connector_type: 'gemini_live',
  status: 'active',
  settings: {
    model: 'gemini-x-live',
    voice: 'Kore',
    thinking_level: null,
    session_budget_eur: null,
    ...DURATIONS,
  },
  model_settings: {
    'gemini-x-live': { voice: 'Kore', thinking_level: null, ...DURATIONS },
    // The thinking model was set up once, with Puck: a switch must recall it.
    'gemini-x-live-extended-thinking': {
      voice: 'Puck',
      thinking_level: 'high',
      idle_timeout_seconds: 120,
      session_max_minutes: 0,
    },
  },
  functionally_verified: true,
  capabilities: CAPABILITIES,
  active: true,
};
const OPENAI = {
  provider: 'openai',
  connector_type: 'gpt_live',
  status: 'active',
  settings: {
    model: 'gpt-x-live',
    voice: 'Marin',
    thinking_level: null,
    session_budget_eur: null,
    ...DURATIONS,
  },
  model_settings: {},
  functionally_verified: true,
  capabilities: { ...CAPABILITIES, configurable_vad: false },
  active: false,
};

const ELEVENLABS = {
  provider: 'elevenlabs',
  connector_type: 'elevenlabs_live',
  status: 'active',
  settings: {
    model: 'agent_0123456789abcdef',
    voice: 'agent',
    thinking_level: null,
    session_budget_eur: null,
    ...DURATIONS,
  },
  model_settings: {},
  functionally_verified: true,
  capabilities: { ...CAPABILITIES, configurable_vad: false, portal_voice: true, vendor_billed: true },
  active: false,
};

describe('LiveModeSettings', () => {
  beforeEach(() => {
    h.liveEnabled = true;
    h.connectors = { connectors: [GEMINI], active_provider: 'gemini' };
    h.models = MODELS;
    h.put.mockReset();
    h.put.mockImplementation(async (_url: string, body: unknown) => body);
    sample.play.mockClear();
  });

  it('renders nothing when the instance flag is off', () => {
    h.liveEnabled = false;
    const { container } = renderWithProviders(<LiveModeSettings lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('points at the connectors section when the account has no connector', () => {
    h.connectors = { connectors: [], active_provider: null };
    renderWithProviders(<LiveModeSettings lng="fr" />);
    expect(screen.getByText('settings.live_mode.connector_missing')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'settings.live_mode.connector_link' })).toHaveAttribute(
      'href',
      expect.stringContaining('section=connectors')
    );
    expect(screen.queryByRole('combobox', { name: 'settings.live_mode.model' })).toBeNull();
  });

  it('saves a changed model with what it remembers through the provider route, and a refusal is an alert', async () => {
    const { user } = renderWithProviders(<LiveModeSettings lng="fr" />);
    const save = screen.getByRole('button', { name: 'settings.live_mode.save' });
    expect(save).toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByRole('combobox', { name: 'settings.live_mode.thinking' })).toBeNull();
    // The billing warning stands above the two durations, bounds published.
    expect(screen.getByRole('note')).toHaveTextContent('settings.live_mode.billing_warning');
    expect(screen.getByLabelText('settings.live_mode.idle_timeout')).toHaveValue(60);
    expect(screen.getByLabelText('settings.live_mode.session_max')).toHaveAttribute('max', '240');
    await user.click(screen.getByRole('combobox', { name: 'settings.live_mode.model' }));
    // The union is grouped under each provider's brand.
    expect(await screen.findByText('Gemini')).toBeInTheDocument();
    await user.click(
      await screen.findByRole('option', { name: 'gemini-x-live-extended-thinking' })
    );
    // The model comes back with its remembered voice, level and durations
    // (owner decision 2026-09-19) — not the voice of the model it replaces.
    expect(
      await screen.findByRole('combobox', { name: 'settings.live_mode.thinking' })
    ).toHaveTextContent('high');
    expect(screen.getByRole('combobox', { name: 'settings.live_mode.voice' })).toHaveTextContent(
      'Puck — Upbeat'
    );
    expect(screen.getByLabelText('settings.live_mode.idle_timeout')).toHaveValue(120);
    expect(screen.getByLabelText('settings.live_mode.session_max')).toHaveValue(0);
    expect(save).toHaveAttribute('aria-disabled', 'false');
    await user.click(save);
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/connectors/gemini', {
        model: 'gemini-x-live-extended-thinking',
        voice: 'Puck',
        thinking_level: 'high',
        idle_timeout_seconds: 120,
        session_max_minutes: 0,
        session_budget_eur: null,
      })
    );

    h.put.mockRejectedValueOnce(
      new ApiError('refused', 422, {
        detail: { code: 'provider_refused', message: 'The provider refused this model: quota' },
      })
    );
    await user.click(screen.getByRole('combobox', { name: 'settings.live_mode.voice' }));
    await user.click(await screen.findByRole('option', { name: 'Kore — Firm' }));
    // A change is heard at once, on the stored key (no key in the call).
    expect(sample.play).toHaveBeenCalledWith('Kore', undefined, 'gemini');
    await user.click(
      screen.getByRole('button', { name: 'settings.live_mode.voice_sample — Kore' })
    );
    expect(sample.play).toHaveBeenCalledTimes(2);
    await user.click(save);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The provider refused this model: quota'
    );
  });

  it("choosing another provider's model lists its voices and saves under that provider", async () => {
    h.connectors = { connectors: [GEMINI, OPENAI], active_provider: 'gemini' };
    const { user } = renderWithProviders(<LiveModeSettings lng="fr" />);
    await user.click(screen.getByRole('combobox', { name: 'settings.live_mode.model' }));
    await user.click(await screen.findByRole('option', { name: 'gpt-x-live' }));
    // The other provider's first voice is taken, and its sample is not forced on the person.
    const voice = screen.getByRole('combobox', { name: 'settings.live_mode.voice' });
    await waitFor(() => expect(voice).toHaveTextContent('Marin — Warm'));
    expect(sample.play).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'settings.live_mode.save' }));
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/connectors/openai', {
        model: 'gpt-x-live',
        voice: 'Marin',
        thinking_level: null,
        ...DURATIONS,
        session_budget_eur: null,
      })
    );
  });

  it('a duration typed by hand is sent as typed, 0 meaning no limit, a refused one withheld', async () => {
    const { user } = renderWithProviders(<LiveModeSettings lng="fr" />);
    const idle = screen.getByLabelText('settings.live_mode.idle_timeout');
    const save = screen.getByRole('button', { name: 'settings.live_mode.save' });
    // Cleared then « 3 » on the way to « 30 »: refused under the field, the save withheld.
    await user.clear(idle);
    expect(idle).toHaveValue(null);
    await user.type(idle, '3');
    expect(idle).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent(
      'settings.live_mode.duration_out_of_bounds'
    );
    expect(save).toHaveAttribute('aria-disabled', 'true');
    await user.click(save);
    expect(h.put).not.toHaveBeenCalled();
    // Cleared then « 0 »: no limit, sent as typed (never « 600 »).
    await user.clear(idle);
    await user.type(idle, '0');
    expect(idle).not.toHaveAttribute('aria-invalid');
    await user.click(save);
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/connectors/gemini', {
        model: 'gemini-x-live',
        voice: 'Kore',
        thinking_level: null,
        idle_timeout_seconds: 0,
        session_max_minutes: 10,
        session_budget_eur: null,
      })
    );
  });

  it('names the discovered models the tariff table does not declare, under the model list', () => {
    h.models = { ...MODELS, unpriced: ['gemini-x-live-undeclared'] };
    renderWithProviders(<LiveModeSettings lng="fr" />);
    const note = screen.getByText('settings.live_mode.unpriced');
    expect(note).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'settings.live_mode.model' })).toHaveAttribute(
      'aria-describedby',
      'live-model-unpriced'
    );
  });

  it('says nothing about undeclared models when every discovered model is declared', () => {
    renderWithProviders(<LiveModeSettings lng="fr" />);
    expect(screen.queryByText('settings.live_mode.unpriced')).toBeNull();
  });

  it('a spend ceiling is optional, sent as typed, refused past the published bound (ADR-300 wave 3)', async () => {
    const { user } = renderWithProviders(<LiveModeSettings lng="fr" />);
    const budget = screen.getByLabelText('settings.live_mode.budget');
    const save = screen.getByRole('button', { name: 'settings.live_mode.save' });
    expect(budget).toHaveValue(null);
    await user.type(budget, '250');
    expect(budget).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('settings.live_mode.budget_out_of_bounds');
    expect(save).toHaveAttribute('aria-disabled', 'true');
    await user.clear(budget);
    await user.type(budget, '2.5');
    expect(budget).not.toHaveAttribute('aria-invalid');
    await user.click(save);
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/connectors/gemini', {
        model: 'gemini-x-live',
        voice: 'Kore',
        thinking_level: null,
        ...DURATIONS,
        session_budget_eur: 2.5,
      })
    );
  });

  it("an agent's voice is the portal's: named by its label, no voice select, no sample (ADR-300 wave 4)", async () => {
    h.connectors = { connectors: [GEMINI, ELEVENLABS], active_provider: 'gemini' };
    const { user } = renderWithProviders(<LiveModeSettings lng="fr" />);
    const model = screen.getByRole('combobox', { name: 'settings.live_mode.model' });
    expect(screen.getByRole('combobox', { name: 'settings.live_mode.voice' })).toBeInTheDocument();
    await user.click(model);
    await user.click(await screen.findByRole('option', { name: 'Assistant' }));
    expect(model).toHaveTextContent('Assistant');
    expect(screen.queryByRole('combobox', { name: 'settings.live_mode.voice' })).toBeNull();
    expect(screen.getByTestId('live-voice-portal')).toHaveTextContent(
      'settings.live_mode.voice_portal'
    );
    expect(sample.play).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'settings.live_mode.save' }));
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/connectors/elevenlabs', {
        model: 'agent_0123456789abcdef',
        voice: 'agent',
        thinking_level: null,
        ...DURATIONS,
        session_budget_eur: null,
      })
    );
  });

  it('does not offer the turn reflexes a provider decides itself', () => {
    h.connectors = {
      connectors: [{ ...OPENAI, active: true }],
      active_provider: 'openai',
    };
    renderWithProviders(<LiveModeSettings lng="fr" />);
    expect(screen.queryByRole('switch', { name: 'settings.live_mode.interruptions' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'settings.live_mode.end_of_speech' })).toBeNull();
    expect(
      screen.getByRole('combobox', { name: 'settings.live_mode.result_delivery' })
    ).toBeVisible();
  });

  it('replaces the whole preferences object on each change', async () => {
    const { user } = renderWithProviders(<LiveModeSettings lng="fr" />);
    await user.click(screen.getByRole('switch', { name: 'settings.live_mode.interruptions' }));
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/preferences', { ...PREFS, interruptions: false })
    );
    await user.click(screen.getByRole('combobox', { name: 'settings.live_mode.end_of_speech' }));
    await user.click(
      await screen.findByRole('option', { name: 'settings.live_mode.end_of_speech_calm' })
    );
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith('/live/preferences', {
        ...PREFS,
        end_of_speech: 'calm',
      })
    );
    expect(
      screen.getByRole('combobox', { name: 'settings.live_mode.end_of_speech' })
    ).toHaveAccessibleDescription('settings.live_mode.end_of_speech_help');
  });
});

/**
 * LiveConnectorForm — key → the listing that validates it fills the model
 * select → voice with its provenance → the thinking level ONLY for a model
 * that declares a ladder → one Activate posting the four fields; a refusal
 * shows the server's sentence in an alert; the key field is labelled.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { useRevisionStore } from '@/stores/revisionStore';

const CAPABILITIES = {
  async_delegation: true,
  delivery_scheduling: true,
  reports_idle: false,
  cancels_on_interruption: true,
  configurable_vad: true,
  resumes: true,
  thinking: false,
};

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, default: { post: api.post, get: api.get }, apiClient: api };
});
const sample = vi.hoisted(() => ({ play: vi.fn(async () => {}), playing: false }));
vi.mock('@/hooks/useVoiceSample', () => ({ useVoiceSample: () => sample }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { LiveConnectorForm } from '../LiveConnectorForm';

const MODELS = {
  models: [
    { provider: 'gemini', name: 'gemini-x-live', thinking_levels: [], capabilities: CAPABILITIES },
    {
      provider: 'gemini',
      name: 'gemini-x-live-extended-thinking',
      thinking_levels: ['low', 'medium', 'high'],
      capabilities: CAPABILITIES,
    },
  ],
  default_model: 'gemini-x-live',
  unpriced: [],
};
const VOICES = {
  provider: 'gemini',
  voices: [
    { name: 'Kore', characteristic: 'Firm' },
    { name: 'Puck', characteristic: 'Upbeat' },
  ],
  provenance: 'published',
  published_at: '2026-09-18',
  source: 'https://example.test/voices',
};

async function typeKeyAndValidate(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.type(screen.getByLabelText('settings.connectors.live.step_key'), 'AIza-test-key');
  await user.click(screen.getByRole('button', { name: 'settings.connectors.live.validate_key' }));
  await screen.findByRole('combobox', { name: 'settings.connectors.live.step_model' });
}

describe('LiveConnectorForm', () => {
  beforeEach(() => {
    api.post.mockReset();
    api.get.mockReset();
    useRevisionStore.setState({ revisions: { live_connectors: 0 } });
    api.post.mockImplementation(async (url: string) => {
      if (url === '/live/models/discover') return MODELS;
      if (url === '/live/connector/activate') return { status: 'active' };
      return {};
    });
    api.get.mockResolvedValue(VOICES);
  });

  it('labels the key, refuses to validate a short one, then lists what the key discovers', async () => {
    const { user } = renderWithProviders(<LiveConnectorForm lng="fr" provider="gemini" />);
    const key = screen.getByLabelText('settings.connectors.live.step_key');
    expect(key).toHaveAttribute('type', 'password');
    const validate = screen.getByRole('button', { name: 'settings.connectors.live.validate_key' });
    expect(validate).toHaveAttribute('aria-disabled', 'true');
    await user.click(validate);
    expect(api.post).not.toHaveBeenCalled();
    await typeKeyAndValidate(user);
    // The form names its provider on both reads — the category is additive.
    expect(api.post).toHaveBeenCalledWith('/live/models/discover', {
      provider: 'gemini',
      api_key: 'AIza-test-key',
    });
    expect(api.get).toHaveBeenCalledWith('/live/voices/published?provider=gemini');
    expect(
      screen.getByRole('combobox', { name: 'settings.connectors.live.step_model' })
    ).toHaveTextContent('gemini-x-live');
    expect(
      screen.getByRole('combobox', { name: 'settings.connectors.live.step_voice' })
    ).toHaveTextContent('Kore — Firm');
    expect(screen.getByText('settings.connectors.live.voices_provenance')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'settings.connectors.live.voices_source' })
    ).toHaveAttribute('href', VOICES.source);
    // The default model declares no ladder: no thinking level is offered.
    expect(
      screen.queryByRole('combobox', { name: 'settings.connectors.live.step_thinking' })
    ).not.toBeInTheDocument();
  });

  it('offers the thinking level only for a model with a ladder, and activates with the four fields', async () => {
    const { user } = renderWithProviders(<LiveConnectorForm lng="fr" provider="gemini" />);
    await typeKeyAndValidate(user);
    await user.click(screen.getByRole('combobox', { name: 'settings.connectors.live.step_model' }));
    await user.click(
      await screen.findByRole('option', { name: 'gemini-x-live-extended-thinking' })
    );
    const thinking = await screen.findByRole('combobox', {
      name: 'settings.connectors.live.step_thinking',
    });
    expect(thinking).toHaveTextContent('low');
    await user.click(thinking);
    await user.click(await screen.findByRole('option', { name: 'high' }));
    await user.click(screen.getByRole('button', { name: 'settings.connectors.live.activate' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/live/connector/activate', {
        provider: 'gemini',
        api_key: 'AIza-test-key',
        model: 'gemini-x-live-extended-thinking',
        voice: 'Kore',
        thinking_level: 'high',
      })
    );
    expect(await screen.findByText('settings.connectors.live.activated')).toBeInTheDocument();
    // The header's voice menu follows the live connectors: an activation declares them changed.
    expect(useRevisionStore.getState().revisions.live_connectors).toBe(1);
  });

  it('sets up an AGENT provider: the agents named, no voice offered, the sentinel posted (ADR-300 wave 4)', async () => {
    api.post.mockImplementation(async (url: string) => {
      if (url === '/live/models/discover')
        return {
          models: [
            {
              provider: 'elevenlabs',
              name: 'agent_0123456789abcdef',
              label: 'Assistant',
              thinking_levels: [],
              capabilities: { ...CAPABILITIES, direct_tools: true, portal_voice: true },
            },
            {
              provider: 'elevenlabs',
              name: 'agent_fedcba9876543210',
              label: 'Support',
              thinking_levels: [],
              capabilities: { ...CAPABILITIES, direct_tools: true, portal_voice: true },
            },
          ],
          default_model: '',
          unpriced: [],
        };
      if (url === '/live/connector/activate') return { status: 'active' };
      return {};
    });
    api.get.mockResolvedValue({ provider: 'elevenlabs', voices: [], provenance: 'portal' });
    const { user } = renderWithProviders(<LiveConnectorForm lng="fr" provider="elevenlabs" />);
    await user.type(screen.getByLabelText('settings.connectors.live.step_key'), 'sk_test_key_1234');
    await user.click(screen.getByRole('button', { name: 'settings.connectors.live.validate_key' }));
    // The step is named after what is chosen: an agent, by its own name.
    const agent = await screen.findByRole('combobox', {
      name: 'settings.connectors.live.step_agent',
    });
    expect(agent).toHaveTextContent('Assistant');
    expect(
      screen.queryByRole('combobox', { name: 'settings.connectors.live.step_voice' })
    ).toBeNull();
    expect(screen.getByTestId('live-voice-portal')).toHaveTextContent(
      'settings.live_mode.voice_portal'
    );
    expect(sample.play).not.toHaveBeenCalled();
    await user.click(agent);
    await user.click(await screen.findByRole('option', { name: 'Support' }));
    await user.click(screen.getByRole('button', { name: 'settings.connectors.live.activate' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/live/connector/activate', {
        provider: 'elevenlabs',
        api_key: 'sk_test_key_1234',
        model: 'agent_fedcba9876543210',
        voice: 'agent',
        thinking_level: null,
      })
    );
  });

  it('shows the server sentence of a refused activation in an alert', async () => {
    api.post.mockImplementation(async (url: string) => {
      if (url === '/live/models/discover') return MODELS;
      throw new ApiError('refused', 422, {
        detail: { code: 'provider_refused', message: 'The provider refused this model: quota' },
      });
    });
    const { user } = renderWithProviders(<LiveConnectorForm lng="fr" provider="gemini" />);
    await typeKeyAndValidate(user);
    await user.click(screen.getByRole('button', { name: 'settings.connectors.live.activate' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The provider refused this model: quota'
    );
    expect(useRevisionStore.getState().revisions.live_connectors).toBe(0);
  });

  it('names the undeclared models of a working key, and offers none', async () => {
    api.post.mockResolvedValue({
      models: [],
      default_model: '',
      unpriced: ['gemini-x-live-undeclared'],
    });
    const { user } = renderWithProviders(<LiveConnectorForm lng="fr" provider="gemini" />);
    await user.type(screen.getByLabelText('settings.connectors.live.step_key'), 'AIza-test-key');
    await user.click(screen.getByRole('button', { name: 'settings.connectors.live.validate_key' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'settings.connectors.live.no_priced_model'
    );
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('names an invalid key and offers no model', async () => {
    api.post.mockResolvedValue({ models: [], default_model: '', unpriced: [] });
    const { user } = renderWithProviders(<LiveConnectorForm lng="fr" provider="gemini" />);
    await user.type(screen.getByLabelText('settings.connectors.live.step_key'), 'AIza-test-key');
    await user.click(screen.getByRole('button', { name: 'settings.connectors.live.validate_key' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'settings.connectors.live.invalid_key'
    );
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'settings.connectors.live.activate' })
    ).toHaveAttribute('aria-disabled', 'true');
  });
});

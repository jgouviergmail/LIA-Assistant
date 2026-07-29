/**
 * AdminLLMConfigSection — golden characterization of the LLM config dialog
 * (audit F011, target #2: LLMConfigDialog CC 86 + TTSProviderConfigBlock CC 30).
 *
 * These tests pin the EXACT current behavior BEFORE the dialog logic is
 * decomposed into pure helpers + sub-components. The critical pin is the
 * PATCH payload built on save: only fields differing from the type's defaults
 * are sent (override diff semantics), with provider_config stable-serialised
 * for TTS types.
 *
 * Harness: the exported section is rendered with useLLMConfig / useApiQuery /
 * i18n mocked (t = key). The dialog opens by clicking a type card. Radix
 * Selects are not driven here (jsdom pointer limitations) — provider/model
 * switch logic is covered by the pure-helper unit tests after extraction.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import AdminLLMConfigSection from '../AdminLLMConfigSection';
import type {
  LLMAgentConfig,
  LLMModelKind,
  LLMTypeConfig,
  ModelCapabilities,
  ProviderKeyStatus,
} from '@/types/llm-config';

// --- mocks -----------------------------------------------------------------

const updateConfig = vi.hoisted(() => vi.fn());
const resetConfig = vi.hoisted(() => vi.fn());
const llmConfigState = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock('@/hooks/useLLMConfig', () => ({
  useLLMConfig: () => llmConfigState.current,
}));

vi.mock('@/hooks/useApiQuery', () => ({
  // Dialog-side queries (ollama models, TTS voices): inert by default —
  // voicesData null → voice pickers fall back to free-text inputs.
  useApiQuery: () => ({ data: null, loading: false }),
}));

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// --- fixtures ----------------------------------------------------------------

const CAPS_FULL: ModelCapabilities = {
  model_id: 'gpt-test',
  kind: 'chat',
  max_output_tokens: 4096,
  supports_tools: true,
  supports_structured_output: true,
  supports_vision: false,
  is_reasoning_model: false,
  reasoning_widget: 'none',
  reasoning_enum_values: null,
  reasoning_budget_range: null,
  reasoning_doc_i18n_key: null,
  effort_values: null,
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  cost_input: null,
  cost_output: null,
};

const CAPS_NO_SAMPLING: ModelCapabilities = {
  ...CAPS_FULL,
  model_id: 'o-strict',
  supports_temperature: false,
  supports_top_p: false,
  supports_frequency_penalty: false,
  supports_presence_penalty: false,
};

const CAPS_ANTHROPIC: ModelCapabilities = {
  ...CAPS_FULL,
  model_id: 'claude-test',
  reasoning_widget: 'enum',
  reasoning_enum_values: ['off', 'low', 'high'],
  effort_values: ['high', 'medium'],
};

const CAPS_TTS_EDGE: ModelCapabilities = { ...CAPS_FULL, model_id: 'edge-tts', kind: 'tts' };
const CAPS_TTS_11L: ModelCapabilities = { ...CAPS_FULL, model_id: 'eleven_v3', kind: 'tts' };

function agentCfg(overrides: Partial<LLMAgentConfig> = {}): LLMAgentConfig {
  return {
    provider: 'openai',
    provider_config: '',
    model: 'gpt-test',
    temperature: 0.7,
    top_p: 1,
    frequency_penalty: 0,
    presence_penalty: 0,
    max_tokens: 1000,
    timeout_seconds: null,
    reasoning_effort: null,
    effort: null,
    ...overrides,
  };
}

function typeConfig(
  llmType: string,
  displayName: string,
  {
    effective = {},
    defaults = {},
    isOverridden = false,
    requiredKind = 'chat' as LLMModelKind,
    requiredCapabilities = [] as string[],
  } = {}
): LLMTypeConfig {
  return {
    llm_type: llmType,
    info: {
      llm_type: llmType,
      display_name: displayName,
      category: 'pipeline',
      description_key: `desc.${llmType}`,
      required_capabilities: requiredCapabilities,
      power_tier: null,
      required_kind: requiredKind,
    },
    effective: agentCfg(effective),
    overrides: {},
    defaults: agentCfg(defaults),
    is_overridden: isOverridden,
  };
}

const PROVIDERS: ProviderKeyStatus[] = [];

function setLLMConfigMock(
  configs: LLMTypeConfig[],
  providers: Record<string, ModelCapabilities[]>
) {
  llmConfigState.current = {
    configs,
    providers: PROVIDERS,
    metadata: { providers },
    loading: false,
    updatingConfig: false,
    updatingKey: false,
    updateConfig,
    resetConfig,
    updateProviderKey: vi.fn(),
    deleteProviderKey: vi.fn(),
  };
}

const METADATA = {
  openai: [CAPS_FULL, CAPS_NO_SAMPLING],
  anthropic: [CAPS_ANTHROPIC],
  edge: [CAPS_TTS_EDGE],
  elevenlabs: [CAPS_TTS_11L],
};

function renderSection(configs: LLMTypeConfig[]) {
  setLLMConfigMock(configs, METADATA);
  return render(<AdminLLMConfigSection lng="en" collapsible={false} />);
}

async function openDialog(cardName: string) {
  fireEvent.click(screen.getByText(cardName));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
  return screen.getByRole('dialog');
}

beforeEach(() => {
  updateConfig.mockReset().mockResolvedValue(undefined);
  resetConfig.mockReset().mockResolvedValue(undefined);
});

// --- cards -------------------------------------------------------------------

describe('type cards', () => {
  it('renders each config as a card with its override state badge', () => {
    renderSection([
      typeConfig('router', 'Router'),
      typeConfig('planner', 'Planner', { isOverridden: true }),
    ]);
    expect(screen.getByText('Router')).toBeTruthy();
    expect(screen.getByText('Planner')).toBeTruthy();
    expect(screen.getAllByText('settings.admin.llmConfig.types.default')).toHaveLength(1);
    expect(screen.getAllByText('settings.admin.llmConfig.types.overridden')).toHaveLength(1);
  });
});

// --- dialog: save diff semantics ----------------------------------------------

describe('dialog save (override diff)', () => {
  it('sends an EMPTY update when nothing was changed', async () => {
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() => expect(updateConfig).toHaveBeenCalledTimes(1));
    expect(updateConfig).toHaveBeenCalledWith('router', {});
  });

  it('sends ONLY the fields that differ from the defaults', async () => {
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    // max_tokens is the first number input (spinbutton) of the dialog.
    const [maxTokens] = screen.getAllByRole('spinbutton');
    fireEvent.change(maxTokens, { target: { value: '2222' } });
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() => expect(updateConfig).toHaveBeenCalledTimes(1));
    expect(updateConfig).toHaveBeenCalledWith('router', { max_tokens: 2222 });
  });

  it('sends a changed slider param (temperature) as a float diff', async () => {
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    // Sliders order: temperature, top_p, frequency_penalty, presence_penalty.
    const [temperature] = screen.getAllByRole('slider');
    fireEvent.change(temperature, { target: { value: '1.3' } });
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() => expect(updateConfig).toHaveBeenCalledTimes(1));
    expect(updateConfig).toHaveBeenCalledWith('router', { temperature: 1.3 });
  });

  it('does not resend a pre-existing override that matches the current form', async () => {
    // effective.temperature 1.5 differs from defaults 0.7 → the form starts at
    // 1.5 and save sends {temperature: 1.5} (unchanged fields stay omitted).
    renderSection([
      typeConfig('router', 'Router', {
        effective: { temperature: 1.5 },
        isOverridden: true,
      }),
    ]);
    await openDialog('Router');
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() => expect(updateConfig).toHaveBeenCalledTimes(1));
    expect(updateConfig).toHaveBeenCalledWith('router', { temperature: 1.5 });
  });
});

// --- dialog: field visibility ---------------------------------------------------

describe('dialog sampling-param visibility', () => {
  it('shows all four sliders for a fully-capable model', async () => {
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');
    expect(screen.getAllByRole('slider')).toHaveLength(4);
    expect(screen.getByText('settings.admin.llmConfig.fields.temperature')).toBeTruthy();
  });

  it('hides every sampling slider when the model supports none of them', async () => {
    renderSection([
      typeConfig('router', 'Router', {
        effective: { model: 'o-strict' },
        defaults: { model: 'o-strict' },
      }),
    ]);
    await openDialog('Router');
    expect(screen.queryAllByRole('slider')).toHaveLength(0);
    expect(screen.queryByText('settings.admin.llmConfig.fields.temperature')).toBeNull();
  });

  it('locks temperature/top_p and shows the constraint note when Anthropic thinking is active', async () => {
    renderSection([
      typeConfig('router', 'Router', {
        effective: {
          provider: 'anthropic',
          model: 'claude-test',
          reasoning_effort: { effort: 'high' },
        },
        defaults: { provider: 'anthropic', model: 'claude-test' },
      }),
    ]);
    await openDialog('Router');
    // temperature + top_p hidden; frequency/presence still shown → 2 sliders.
    expect(screen.getAllByRole('slider')).toHaveLength(2);
    expect(screen.getByText('settings.admin.llmConfig.constraints.reasoningTemp')).toBeTruthy();
  });

  it('shows the global effort selector only when the model declares effort_values', async () => {
    renderSection([
      typeConfig('router', 'Router', {
        effective: { provider: 'anthropic', model: 'claude-test' },
        defaults: { provider: 'anthropic', model: 'claude-test' },
      }),
      typeConfig('other', 'Other'),
    ]);
    await openDialog('Router');
    expect(screen.getByText('settings.admin.llmConfig.fields.effort')).toBeTruthy();
  });

  it('marks a field with the overridden badge when it differs from the default', async () => {
    renderSection([
      typeConfig('router', 'Router', {
        effective: { temperature: 1.5 },
        isOverridden: true,
      }),
    ]);
    const dialog = await openDialog('Router');
    // The dialog renders in its own portal (excludes the card's badge): the
    // temperature field carries its own "overridden" badge.
    const badges = within(dialog as HTMLElement).queryAllByText(
      'settings.admin.llmConfig.types.overridden'
    );
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });
});

// --- dialog: reset ---------------------------------------------------------------

describe('dialog reset', () => {
  it('disables reset for non-overridden configs', async () => {
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');
    const reset = screen
      .getByText('settings.admin.llmConfig.config.resetButton')
      .closest('button')!;
    expect(reset.disabled).toBe(true);
  });

  it('calls resetConfig for overridden configs', async () => {
    renderSection([
      typeConfig('router', 'Router', { effective: { temperature: 1.5 }, isOverridden: true }),
    ]);
    await openDialog('Router');
    fireEvent.click(screen.getByText('settings.admin.llmConfig.config.resetButton'));
    await waitFor(() => expect(resetConfig).toHaveBeenCalledWith('router'));
  });
});

// --- dialog: TTS provider config -----------------------------------------------

describe('TTS provider config block', () => {
  function ttsConfig(provider: string, model: string, providerConfig = '') {
    return typeConfig('voice_tts', 'Voice TTS', {
      effective: { provider, model, provider_config: providerConfig },
      defaults: { provider, model, provider_config: providerConfig },
      requiredKind: 'tts',
    });
  }

  it('renders the edge tuning block (rate/pitch/volume) with free-text voice inputs', async () => {
    renderSection([ttsConfig('edge', 'edge-tts')]);
    await openDialog('Voice TTS');
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.sectionTitle')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.rate')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.pitch')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.volume')).toBeTruthy();
    // voicesData is null in this harness → both pickers are free-text inputs.
    expect(
      screen.getAllByPlaceholderText('settings.admin.llmConfig.voiceTts.voiceIdPlaceholder')
    ).toHaveLength(2);
  });

  it('renders the elevenlabs tuning block (voice_settings sliders + speaker boost)', async () => {
    renderSection([ttsConfig('elevenlabs', 'eleven_v3')]);
    await openDialog('Voice TTS');
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.stability')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.similarityBoost')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.style')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.useSpeakerBoost')).toBeTruthy();
    expect(screen.getByText('settings.admin.llmConfig.voiceTts.outputFormat')).toBeTruthy();
  });

  it('saves the TTS tuning as a stable-serialised provider_config diff', async () => {
    renderSection([ttsConfig('edge', 'edge-tts')]);
    await openDialog('Voice TTS');

    const [rate] = screen.getAllByPlaceholderText('+10%');
    fireEvent.change(rate, { target: { value: '+25%' } });
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() => expect(updateConfig).toHaveBeenCalledTimes(1));
    expect(updateConfig).toHaveBeenCalledWith('voice_tts', {
      provider_config: '{"rate":"+25%"}',
    });
  });

  it('does not send provider_config when the tuning matches the default blob', async () => {
    renderSection([ttsConfig('edge', 'edge-tts', '{"rate":"+10%"}')]);
    await openDialog('Voice TTS');
    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() => expect(updateConfig).toHaveBeenCalledTimes(1));
    expect(updateConfig).toHaveBeenCalledWith('voice_tts', {});
  });
});

describe('accessible names on dialog controls (audit F012)', () => {
  function ttsConfig(provider: string, model: string, providerConfig = '') {
    return typeConfig('voice_tts', 'Voice TTS', {
      effective: { provider, model, provider_config: providerConfig },
      defaults: { provider, model, provider_config: providerConfig },
      requiredKind: 'tts',
    });
  }

  it('sampling sliders are named by their visible labels and operable', async () => {
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    // getByRole('slider', {name}) proves the programmatic association
    // (aria-labelledby -> the visible <Label>), not just label proximity.
    const temperature = screen.getByRole('slider', {
      name: 'settings.admin.llmConfig.fields.temperature',
    });
    expect(
      screen.getByRole('slider', { name: 'settings.admin.llmConfig.fields.topP' })
    ).toBeTruthy();

    // Nominal: the named control is the real input (value change flows).
    fireEvent.change(temperature, { target: { value: '0.9' } });
    expect((temperature as HTMLInputElement).value).toBe('0.9');

    // Focus: the named control is focusable.
    temperature.focus();
    expect(document.activeElement).toBe(temperature);
  });

  it('elevenlabs voice sliders and the speaker-boost checkbox are named and operable', async () => {
    renderSection([ttsConfig('elevenlabs', 'eleven_v3')]);
    await openDialog('Voice TTS');

    for (const key of ['stability', 'similarityBoost', 'style'] as const) {
      expect(
        screen.getByRole('slider', { name: `settings.admin.llmConfig.voiceTts.${key}` })
      ).toBeTruthy();
    }

    const boost = screen.getByRole('checkbox', {
      name: 'settings.admin.llmConfig.voiceTts.useSpeakerBoost',
    }) as HTMLInputElement;
    const before = boost.checked;
    fireEvent.click(boost);
    expect(boost.checked).toBe(!before);

    boost.focus();
    expect(document.activeElement).toBe(boost);
  });
});

// --- dialog save: structured 422 surfacing ------------------------------------
//
// Regression class (prod 2026-07-29): the backend rejects a thinking-enabled
// config whose effective max_tokens sits below the safety floor with an
// explicit structured 422 — but the old catch swallowed it behind a generic
// "save failed" toast, leaving the admin blind to the actual constraint.

describe('dialog save (structured 422 surfacing)', () => {
  it('shows the localized explicit message for thinking_budget_below_floor', async () => {
    const { toast } = await import('sonner');
    updateConfig.mockRejectedValueOnce(
      Object.assign(new Error('422'), {
        data: {
          detail: {
            type: 'thinking_budget_below_floor',
            msg: 'raw backend msg',
            ctx: { floor: 4000, effective_max_tokens: 600 },
          },
        },
      })
    );
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'settings.admin.llmConfig.config.thinkingBudgetBelowFloor'
      )
    );
  });

  it('surfaces other structured msgs as the description of the generic toast', async () => {
    const { toast } = await import('sonner');
    updateConfig.mockRejectedValueOnce(
      Object.assign(new Error('422'), {
        data: {
          detail: { type: 'invalid_reasoning_effort', msg: 'explicit matrix message', ctx: {} },
        },
      })
    );
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.admin.llmConfig.config.error', {
        description: 'explicit matrix message',
      })
    );
  });

  it('keeps the generic toast for unstructured failures', async () => {
    const { toast } = await import('sonner');
    updateConfig.mockRejectedValueOnce(new Error('network down'));
    renderSection([typeConfig('router', 'Router')]);
    await openDialog('Router');

    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.admin.llmConfig.config.error')
    );
  });
});

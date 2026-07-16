/**
 * ModelPricingModal — golden characterization (audit F011).
 *
 * Pins the modal's behavior contract BEFORE the CC-65 form is split into
 * per-section sub-components: the submit payload (the critical invariant —
 * cached_input_unit_price coerced to null when blank), add vs edit mode, the
 * provider immutability in edit, the reasoning gating (is_reasoning_model →
 * template selector), the custom-shape conditional inputs, and the
 * kind→pricing_unit re-alignment. The form uses native <select>/<input>, so
 * changes are driven directly in jsdom.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { ModelPricingModal } from '../AdminLLMPricingSection';
import type { LLMModelPricing } from '../AdminLLMPricingSection';

// Radix Switch measures itself via ResizeObserver, absent from jsdom.
vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
);

const fetchReasoningTemplates = vi.hoisted(() => vi.fn());
vi.mock('@/lib/actions/settings-actions', () => ({
  fetchReasoningTemplates,
  // Unused by the modal but imported by the host module.
  createLLMPricing: vi.fn(),
  updateLLMPricing: vi.fn(),
  deactivateLLMPricing: vi.fn(),
  reloadLLMPricingCache: vi.fn(),
}));

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { name?: string }) => (opts?.name ? `${key}:${opts.name}` : key),
  }),
}));

vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn() } }));

const TEMPLATES = [
  {
    template_model_name: 'o1',
    description: 'OpenAI o-series (enum effort)',
    is_reasoning_model: true,
    reasoning_widget: 'enum' as const,
    reasoning_enum_values: ['low', 'high'],
    reasoning_budget_range: null,
  },
];

function editModel(overrides: Partial<LLMModelPricing> = {}): LLMModelPricing {
  return {
    id: 'm1',
    provider: 'anthropic',
    model_name: 'claude-x',
    kind: 'chat',
    max_input_tokens: 200000,
    max_output_tokens: 8192,
    supports_tools: true,
    supports_structured_output: true,
    supports_strict_mode: false,
    supports_streaming: true,
    supports_vision: true,
    is_reasoning_model: false,
    reasoning_widget: 'none',
    reasoning_enum_values: null,
    reasoning_budget_range: null,
    reasoning_doc_i18n_key: null,
    supports_temperature: true,
    supports_top_p: true,
    supports_frequency_penalty: true,
    supports_presence_penalty: true,
    pricing_unit: 'per_1m_tokens',
    input_unit_price: '3.0',
    cached_input_unit_price: '0.3',
    output_unit_price: '15.0',
    ...overrides,
  } as LLMModelPricing;
}

function renderModal(model: LLMModelPricing | null) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  render(<ModelPricingModal lng="en" model={model} onClose={onClose} onSubmit={onSubmit} />);
  return { onSubmit, onClose };
}

const submit = () => fireEvent.click(screen.getByText('settings.admin.llm.modal.submit_create'));
const submitEdit = () => fireEvent.click(screen.getByText('settings.admin.llm.modal.submit_edit'));

beforeEach(() => {
  fetchReasoningTemplates.mockReset().mockResolvedValue(TEMPLATES);
});

describe('add mode', () => {
  it('renders the add title and submits the default form with a null blank cached price', () => {
    const { onSubmit } = renderModal(null);
    expect(screen.getByText('settings.admin.llm.modal.title_add')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('settings.admin.llm.modal.model_name_label'), {
      target: { value: 'gpt-new' },
    });
    fireEvent.change(screen.getByLabelText(/input_price_label/), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText(/output_price_label/), { target: { value: '6.0' } });
    submit();

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.model_name).toBe('gpt-new');
    expect(payload.input_unit_price).toBe('1.5');
    expect(payload.output_unit_price).toBe('6.0');
    // Blank cached price → null (the critical submit coercion).
    expect(payload.cached_input_unit_price).toBeNull();
    expect(payload.provider).toBe('openai'); // default
  });

  it('re-aligns pricing_unit when the kind changes to an audio kind', () => {
    const { onSubmit } = renderModal(null);
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'tts' } });
    fireEvent.change(screen.getByLabelText('settings.admin.llm.modal.model_name_label'), {
      target: { value: 'x' },
    });
    fireEvent.change(screen.getByLabelText(/input_price_label/), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/output_price_label/), { target: { value: '1' } });
    submit();
    expect(onSubmit.mock.calls[0][0].kind).toBe('tts');
    expect(onSubmit.mock.calls[0][0].pricing_unit).toBe('per_audio_hour');
  });
});

describe('edit mode', () => {
  it('renders the edit title, makes provider immutable, and preserves the cached price', () => {
    const { onSubmit } = renderModal(editModel());
    expect(screen.getByText('settings.admin.llm.modal.title_edit:claude-x')).toBeTruthy();

    const provider = screen.getByLabelText(
      'settings.admin.llm.modal.provider_label'
    ) as HTMLSelectElement;
    expect(provider.disabled).toBe(true);
    expect(provider.value).toBe('anthropic');

    submitEdit();
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.provider).toBe('anthropic');
    expect(payload.cached_input_unit_price).toBe('0.3'); // preserved (non-blank)
    expect(payload.model_name).toBe('claude-x');
  });

  it('coerces a cleared cached price to null on submit', () => {
    const { onSubmit } = renderModal(editModel());
    fireEvent.change(screen.getByLabelText(/cached_input_label/), { target: { value: '' } });
    submitEdit();
    expect(onSubmit.mock.calls[0][0].cached_input_unit_price).toBeNull();
  });
});

describe('reasoning gating + custom shape', () => {
  it('hides the reasoning shape controls for a non-reasoning model (gating off)', () => {
    // The template selector and the custom-shape block are gated by
    // is_reasoning_model (off by default in add mode). The gating-ON direction
    // is covered by the "custom shape" tests below, which toggle it on and then
    // find + drive the reasoning-widget controls.
    renderModal(null);
    expect(screen.queryByLabelText('Reasoning widget')).toBeNull();
    expect(screen.queryByText('Copy reasoning shape from')).toBeNull();
  });

  it('shows the enum CSV input in custom mode with widget=enum', () => {
    renderModal(null);
    fireEvent.click(screen.getByLabelText('Is reasoning model'));
    // Default template is Custom → the custom shape block is shown.
    fireEvent.change(screen.getByLabelText('Reasoning widget'), { target: { value: 'enum' } });
    expect(screen.getByLabelText('Enum values (comma-separated)')).toBeTruthy();
    // Switching to a budget widget swaps to the budget fields.
    fireEvent.change(screen.getByLabelText('Reasoning widget'), {
      target: { value: 'budget_int' },
    });
    expect(screen.queryByLabelText('Enum values (comma-separated)')).toBeNull();
    expect(screen.getByLabelText('Budget min')).toBeTruthy();
    expect(screen.getByLabelText('Budget max')).toBeTruthy();
  });

  it('emits enum values parsed from CSV in the submit payload', () => {
    const { onSubmit } = renderModal(null);
    fireEvent.change(screen.getByLabelText('settings.admin.llm.modal.model_name_label'), {
      target: { value: 'm' },
    });
    fireEvent.change(screen.getByLabelText(/input_price_label/), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/output_price_label/), { target: { value: '1' } });
    fireEvent.click(screen.getByLabelText('Is reasoning model'));
    fireEvent.change(screen.getByLabelText('Reasoning widget'), { target: { value: 'enum' } });
    fireEvent.change(screen.getByLabelText('Enum values (comma-separated)'), {
      target: { value: 'low, high' },
    });
    submit();
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.is_reasoning_model).toBe(true);
    expect(payload.reasoning_widget).toBe('enum');
    expect(payload.reasoning_enum_values_csv).toBe('low, high');
  });
});

describe('capability toggles', () => {
  it('reflects a capability switch in the submit payload', () => {
    const { onSubmit } = renderModal(editModel({ supports_vision: true }));
    // supports_vision starts true; toggling flips it.
    fireEvent.click(screen.getByLabelText('settings.admin.llm.modal.supports_vision_label'));
    submitEdit();
    expect(onSubmit.mock.calls[0][0].supports_vision).toBe(false);
  });
});

describe('edit mode with a reasoning model', () => {
  it('renders without crashing and fetches the template list', async () => {
    const reasoningRow = editModel({
      is_reasoning_model: true,
      reasoning_widget: 'enum',
      reasoning_enum_values: ['low', 'high'],
      reasoning_budget_range: null,
    });
    renderModal(reasoningRow);
    // The reasoning section renders for a reasoning row; the template list is
    // fetched once on mount (the fingerprint auto-select behavior lives in the
    // unchanged fetch effect and is out of this decomposition's scope).
    await waitFor(() => expect(fetchReasoningTemplates).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('Is reasoning model')).toBeTruthy();
  });
});

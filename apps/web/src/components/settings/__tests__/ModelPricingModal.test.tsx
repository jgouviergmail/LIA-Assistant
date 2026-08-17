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
    t: (key: string, opts?: { name?: string; index?: number }) =>
      opts?.name ? `${key}:${opts.name}` : opts?.index !== undefined ? `${key}:${opts.index}` : key,
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

// Shared domain factory — the same row shape drives
// AdminLLMPricingSection.test.tsx.
import { makeLLMPricing as editModel } from '@/__tests__/factories';

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

describe('time-slot tariffs (ADR-223)', () => {
  const toggleSlots = () =>
    fireEvent.click(screen.getByLabelText('settings.admin.llm.modal.time_slots_toggle_label'));

  const fillSlotRow = (index: number, over: Partial<Record<string, string>> = {}) => {
    const values: Record<string, string> = {
      start: '01:00',
      end: '04:00',
      input_unit_price: '0.44',
      output_unit_price: '1.32',
      ...over,
    };
    for (const [suffix, value] of Object.entries(values)) {
      const input = document.getElementById(`time-slot-${index}-${suffix}`);
      expect(input).toBeTruthy();
      fireEvent.change(input!, { target: { value } });
    }
  };

  const fillBasePrices = () => {
    fireEvent.change(screen.getByLabelText('settings.admin.llm.modal.model_name_label'), {
      target: { value: 'deepseek-v4-flash' },
    });
    fireEvent.change(screen.getByLabelText(/input_price_label/), { target: { value: '0.22' } });
    fireEvent.change(screen.getByLabelText(/output_price_label/), { target: { value: '0.66' } });
  };

  it('is off by default and absent from an audio-billed form', () => {
    renderModal(null);
    expect(
      screen.getByLabelText('settings.admin.llm.modal.time_slots_toggle_label')
    ).toBeTruthy();
    // Switching kind to tts re-aligns pricing_unit to per_audio_hour and the
    // whole block disappears — audio always bills flat.
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'tts' } });
    expect(
      screen.queryByLabelText('settings.admin.llm.modal.time_slots_toggle_label')
    ).toBeNull();
  });

  it('seeds one editable row on enable and submits the typed windows', () => {
    const { onSubmit } = renderModal(null);
    fillBasePrices();
    toggleSlots();
    fillSlotRow(0);
    submit();

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.time_slots_enabled).toBe(true);
    expect(payload.time_slots).toEqual([
      {
        start_utc: '01:00',
        end_utc: '04:00',
        input_unit_price: '0.44',
        cached_input_unit_price: '',
        output_unit_price: '1.32',
      },
    ]);
  });

  it('blocks submit and announces the error when every row was removed', () => {
    // A row with empty required fields is stopped by NATIVE constraint
    // validation before the custom guard (both jsdom and real browsers);
    // the reachable 'incomplete' case is an emptied row list — no required
    // field remains, so only the guard stands between the admin and a
    // windowed tariff with zero windows.
    const { onSubmit } = renderModal(null);
    fillBasePrices();
    toggleSlots();
    fireEvent.click(
      screen.getByLabelText('settings.admin.llm.modal.time_slots_remove:1', { exact: false })
    );
    submit();

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toBe(
      'settings.admin.llm.modal.time_slots_error_incomplete'
    );

    // Adding a complete row clears the error live and unblocks the submit.
    fireEvent.click(screen.getByText('settings.admin.llm.modal.time_slots_add'));
    fillSlotRow(0);
    expect(screen.queryByRole('alert')).toBeNull();
    submit();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('rejects overlapping windows with the dedicated message', () => {
    const { onSubmit } = renderModal(null);
    fillBasePrices();
    toggleSlots();
    fillSlotRow(0);
    fireEvent.click(screen.getByText('settings.admin.llm.modal.time_slots_add'));
    fillSlotRow(1, { start: '03:00', end: '05:00' });
    submit();

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toBe(
      'settings.admin.llm.modal.time_slots_error_overlap'
    );
  });

  it('seeds the editor from an existing windowed model and clears via the toggle', () => {
    const { onSubmit } = renderModal(
      editModel({
        time_slots: [
          {
            start_utc: '06:00',
            end_utc: '10:00',
            input_unit_price: '0.44',
            cached_input_unit_price: null,
            output_unit_price: '1.32',
          },
        ],
      })
    );

    const start = document.getElementById('time-slot-0-start') as HTMLInputElement;
    expect(start.value).toBe('06:00');

    // Toggling off keeps the rows in state but submits enabled=false — the
    // section maps that to the [] clearing sentinel on the wire.
    toggleSlots();
    submitEdit();
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.time_slots_enabled).toBe(false);
    expect(payload.time_slots).toHaveLength(1);
  });

  it('removes a window row via its labelled remove button', () => {
    renderModal(null);
    toggleSlots();
    fireEvent.click(screen.getByText('settings.admin.llm.modal.time_slots_add'));
    expect(document.getElementById('time-slot-1-start')).toBeTruthy();

    fireEvent.click(
      screen.getByLabelText('settings.admin.llm.modal.time_slots_remove:2', { exact: false })
    );
    expect(document.getElementById('time-slot-1-start')).toBeNull();
  });
});

describe('mobile scroll architecture', () => {
  it('scrolls on the overlay and centers via a min-h-full wrapper, never on the flex container itself', () => {
    // Regression pin for the phone-height bug: with `items-center` and
    // `overflow-y-auto` on the SAME element, a panel taller than the
    // viewport is centered first and clipped above the scroll origin —
    // the form's first fields become unreachable and the dialog cannot
    // be submitted (measured at 390x844: title at -349px, half the
    // scroll range lost). The cure is structural and CSS-only, so the
    // oracle is structural: the overlay owns the scroll, an inner
    // min-h-full wrapper owns the centering.
    renderModal(null);
    const overlay = screen.getByRole('dialog');
    expect(overlay.className).toContain('overflow-y-auto');
    expect(overlay.className).not.toContain('items-center');
    const wrapper = overlay.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain('min-h-full');
    expect(wrapper.className).toContain('items-center');
  });
});

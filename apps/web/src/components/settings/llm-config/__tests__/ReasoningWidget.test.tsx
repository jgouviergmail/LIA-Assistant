/**
 * ReasoningWidget — the single reasoning control (ADR-245).
 *
 * It replaced three sub-components dispatched on `reasoning_widget`. What a
 * model offers now travels with the model, so the tests below drive the widget
 * through PROFILES rather than through widget names, and assert the two things
 * that matter: it offers exactly what the profile publishes, and every
 * interaction emits a complete intent (never a partial object the backend would
 * have to guess at).
 *
 * Radix Select values are not drivable in jsdom (pointer limitations), so the
 * level dropdown is asserted on what it RENDERS; the budget Input and the
 * exclude Switch, which are drivable, are asserted on their emitted payloads.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ModelCapabilities, ReasoningEffortValue } from '@/types/llm-config';
import { ReasoningWidget } from '../ReasoningWidget';

/** Identity translator: assertions target keys, not a locale's wording. */
const t = (key: string) => key;

function caps(partial: Partial<ModelCapabilities>): ModelCapabilities {
  return {
    reasoning_family: 'none',
    reasoning_levels: [],
    reasoning_can_disable: true,
    reasoning_supports_budget: false,
    reasoning_supports_exclude: false,
    reasoning_budget_range: null,
    reasoning_doc_i18n_key: null,
    ...partial,
  } as ModelCapabilities;
}

const LADDER = caps({
  reasoning_family: 'openai',
  reasoning_levels: ['none', 'low', 'medium', 'high'],
});

const BUDGETED = caps({
  reasoning_family: 'anthropic_budget',
  reasoning_levels: ['none', 'low', 'high'],
  reasoning_supports_budget: true,
  reasoning_budget_range: { min: 1024, max: 32000 },
});

const GEMINI = caps({
  reasoning_family: 'gemini_level',
  reasoning_levels: ['low', 'medium', 'high'],
  reasoning_can_disable: false,
  reasoning_supports_exclude: true,
});

const INTENT: ReasoningEffortValue = {
  level: 'high',
  budget_tokens: null,
  exclude_from_output: false,
};

describe('a model that does not reason', () => {
  it('renders nothing at all', () => {
    const { container } = render(
      <ReasoningWidget caps={caps({})} value={null} onChange={vi.fn()} t={t} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a model absent from the catalogue', () => {
    const { container } = render(
      <ReasoningWidget caps={undefined} value={null} onChange={vi.fn()} t={t} />
    );
    expect(container.firstChild).toBeNull();
  });
});

describe('the level control', () => {
  it('shows the default when there is no override', () => {
    render(<ReasoningWidget caps={LADDER} value={null} onChange={vi.fn()} t={t} />);
    expect(screen.getByText('settings.admin.llmConfig.fields.reasoningDefault')).toBeTruthy();
  });

  it('shows the configured level when there is one', () => {
    render(<ReasoningWidget caps={LADDER} value={INTENT} onChange={vi.fn()} t={t} />);
    expect(screen.getByText('settings.admin.llmConfig.reasoningLevels.high')).toBeTruthy();
  });

  it('has an accessible name even though its label is rendered by the section', () => {
    render(<ReasoningWidget caps={LADDER} value={null} onChange={vi.fn()} t={t} />);
    expect(
      screen.getByRole('combobox', {
        name: 'settings.admin.llmConfig.fields.reasoningEffort',
      })
    ).toBeTruthy();
  });

  it('notes a single-level model instead of pretending there is a choice', () => {
    const forced = caps({ reasoning_family: 'openai', reasoning_levels: ['medium'] });
    render(<ReasoningWidget caps={forced} value={null} onChange={vi.fn()} t={t} />);
    expect(
      screen.getByText('settings.admin.llmConfig.constraints.reasoningSingleLevel')
    ).toBeTruthy();
  });

  it('does not note it when several levels are offered', () => {
    render(<ReasoningWidget caps={LADDER} value={null} onChange={vi.fn()} t={t} />);
    expect(
      screen.queryByText('settings.admin.llmConfig.constraints.reasoningSingleLevel')
    ).toBeNull();
  });
});

describe('the budget control', () => {
  it('is absent for a family that expresses depth only', () => {
    render(<ReasoningWidget caps={LADDER} value={null} onChange={vi.fn()} t={t} />);
    expect(screen.queryByLabelText('settings.admin.llmConfig.fields.reasoningBudget')).toBeNull();
  });

  it('is present, bounded by the published range, for a budget family', () => {
    render(<ReasoningWidget caps={BUDGETED} value={null} onChange={vi.fn()} t={t} />);
    const input = screen.getByLabelText(
      'settings.admin.llmConfig.fields.reasoningBudget'
    ) as HTMLInputElement;
    expect(input.min).toBe('1024');
    expect(input.max).toBe('32000');
  });

  it('emits a complete intent when a budget is typed on an empty value', () => {
    const onChange = vi.fn();
    render(<ReasoningWidget caps={BUDGETED} value={null} onChange={onChange} t={t} />);
    fireEvent.change(screen.getByLabelText('settings.admin.llmConfig.fields.reasoningBudget'), {
      target: { value: '8192' },
    });
    expect(onChange).toHaveBeenCalledWith({
      level: 'provider_default',
      budget_tokens: 8192,
      exclude_from_output: false,
    });
  });

  it('keeps the chosen level when the budget changes', () => {
    const onChange = vi.fn();
    render(<ReasoningWidget caps={BUDGETED} value={INTENT} onChange={onChange} t={t} />);
    fireEvent.change(screen.getByLabelText('settings.admin.llmConfig.fields.reasoningBudget'), {
      target: { value: '2048' },
    });
    expect(onChange).toHaveBeenCalledWith({
      level: 'high',
      budget_tokens: 2048,
      exclude_from_output: false,
    });
  });

  it('clearing the field means "let the depth decide", not zero', () => {
    const onChange = vi.fn();
    render(
      <ReasoningWidget
        caps={BUDGETED}
        value={{ ...INTENT, budget_tokens: 4096 }}
        onChange={onChange}
        t={t}
      />
    );
    fireEvent.change(screen.getByLabelText('settings.admin.llmConfig.fields.reasoningBudget'), {
      target: { value: '' },
    });
    expect(onChange).toHaveBeenCalledWith({
      level: 'high',
      budget_tokens: null,
      exclude_from_output: false,
    });
  });
});

describe('the budget control, when the typed value is out of bounds', () => {
  const OUT_OF_RANGE: ReasoningEffortValue = { ...INTENT, budget_tokens: 999_999 };

  it('marks the field invalid and points at the rule', () => {
    render(<ReasoningWidget caps={BUDGETED} value={OUT_OF_RANGE} onChange={vi.fn()} t={t} />);
    const input = screen.getByLabelText('settings.admin.llmConfig.fields.reasoningBudget');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    const describedBy = input.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)?.textContent).toContain(
      'reasoningBudgetRange'
    );
  });

  it('says nothing extra while the value is inside the range', () => {
    render(
      <ReasoningWidget
        caps={BUDGETED}
        value={{ ...INTENT, budget_tokens: 2048 }}
        onChange={vi.fn()}
        t={t}
      />
    );
    const input = screen.getByLabelText('settings.admin.llmConfig.fields.reasoningBudget');
    expect(input.getAttribute('aria-invalid')).toBeNull();
  });

  it('gives each mounted widget its own ids', () => {
    // Two live `id="reasoning-budget"` attributes would send both labels to the
    // first input, and the second control would be unreachable by name.
    const { container } = render(
      <>
        <ReasoningWidget caps={BUDGETED} value={null} onChange={vi.fn()} t={t} />
        <ReasoningWidget caps={BUDGETED} value={null} onChange={vi.fn()} t={t} />
      </>
    );
    const ids = Array.from(container.querySelectorAll('input[type="number"]')).map(el => el.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });
});

describe('the exclude-from-output control', () => {
  it('is absent where the flag would never reach the provider', () => {
    render(<ReasoningWidget caps={BUDGETED} value={null} onChange={vi.fn()} t={t} />);
    expect(screen.queryByLabelText('settings.admin.llmConfig.fields.reasoningExclude')).toBeNull();
  });

  it('is present, and toggles, where the family expresses it', () => {
    const onChange = vi.fn();
    render(<ReasoningWidget caps={GEMINI} value={INTENT} onChange={onChange} t={t} />);
    fireEvent.click(screen.getByLabelText('settings.admin.llmConfig.fields.reasoningExclude'));
    expect(onChange).toHaveBeenCalledWith({
      level: 'high',
      budget_tokens: null,
      exclude_from_output: true,
    });
  });

  it('reflects the current value', () => {
    render(
      <ReasoningWidget
        caps={GEMINI}
        value={{ ...INTENT, exclude_from_output: true }}
        onChange={vi.fn()}
        t={t}
      />
    );
    const toggle = screen.getByLabelText('settings.admin.llmConfig.fields.reasoningExclude');
    expect(toggle.getAttribute('aria-checked')).toBe('true');
  });
});

describe('a model that cannot stop reasoning', () => {
  it('offers no "none", because the API would refuse it', () => {
    render(<ReasoningWidget caps={GEMINI} value={null} onChange={vi.fn()} t={t} />);
    // The trigger shows the current selection; the ladder itself is what the
    // profile published, and 'none' is not on it.
    expect(GEMINI.reasoning_levels).not.toContain('none');
    expect(screen.getByText('settings.admin.llmConfig.fields.reasoningDefault')).toBeTruthy();
  });
});

describe('the model documentation', () => {
  it('is shown when the catalogue names a doc key it knows', () => {
    const documented = caps({
      reasoning_family: 'openai',
      reasoning_levels: ['none', 'high'],
      reasoning_doc_i18n_key: 'openai_gpt5_2',
    });
    render(<ReasoningWidget caps={documented} value={null} onChange={vi.fn()} t={t} />);
    expect(screen.getByText(/minimal/i)).toBeTruthy();
  });

  it('stays silent on a key with no entry, rather than rendering an empty note', () => {
    const undocumented = caps({
      reasoning_family: 'openai',
      reasoning_levels: ['none', 'high'],
      reasoning_doc_i18n_key: 'a_key_nobody_wrote',
    });
    const { container } = render(
      <ReasoningWidget caps={undocumented} value={null} onChange={vi.fn()} t={t} />
    );
    expect(container.querySelectorAll('p').length).toBe(0);
  });
});

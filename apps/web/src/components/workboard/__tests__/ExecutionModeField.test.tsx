/**
 * The execution mode, chosen per ticket and per routine (ADR-276, lot 10, D81;
 * « auto » ADR-390): the header menu's own words AND marks, and a choice
 * narrowed to the three modes the type knows without a cast.
 */
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ExecutionModeField } from '@/components/workboard/ExecutionModeField';

describe('ExecutionModeField', () => {
  it('offers the three modes under the header menu marks', async () => {
    const { user } = renderWithProviders(
      <ExecutionModeField id="mode" value="react" onChange={vi.fn()} />
    );

    const trigger = screen.getByRole('combobox', { name: 'workboard.form.execution_mode' });
    expect(trigger).toHaveTextContent('executionMode.modes.react');
    expect(trigger.querySelector('.lucide-zap')).not.toBeNull();

    await user.click(trigger);
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual([
      'executionMode.modes.pipeline',
      'executionMode.modes.react',
      'executionMode.modes.auto',
    ]);
    expect(options[0].querySelector('.lucide-workflow')).not.toBeNull();
    expect(options[1].querySelector('.lucide-zap')).not.toBeNull();
    expect(options[2].querySelector('.lucide-split')).not.toBeNull();
  });

  it.each(['pipeline', 'auto'] as const)('reports the chosen mode (%s)', async mode => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <ExecutionModeField id="mode" value="react" onChange={onChange} />
    );

    await user.click(screen.getByRole('combobox', { name: 'workboard.form.execution_mode' }));
    await user.click(await screen.findByRole('option', { name: `executionMode.modes.${mode}` }));

    expect(onChange).toHaveBeenCalledWith(mode);
  });
});

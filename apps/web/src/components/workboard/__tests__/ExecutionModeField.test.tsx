/**
 * The execution mode, chosen per ticket (ADR-276, lot 10, D81): the header
 * toggle's own words AND marks, and a choice narrowed to the two modes the
 * type knows without a cast.
 */
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ExecutionModeField } from '@/components/workboard/ExecutionModeField';

describe('ExecutionModeField', () => {
  it('offers the two modes under the header toggle marks', async () => {
    const { user } = renderWithProviders(
      <ExecutionModeField id="mode" value="react" onChange={vi.fn()} />
    );

    const trigger = screen.getByRole('combobox', { name: 'workboard.form.execution_mode' });
    expect(trigger).toHaveTextContent('workboard.execution_mode.react');
    expect(trigger.querySelector('.lucide-zap')).not.toBeNull();

    await user.click(trigger);
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual([
      'workboard.execution_mode.react',
      'workboard.execution_mode.pipeline',
    ]);
    expect(options[0].querySelector('.lucide-zap')).not.toBeNull();
    expect(options[1].querySelector('.lucide-workflow')).not.toBeNull();
  });

  it('reports the chosen mode', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <ExecutionModeField id="mode" value="react" onChange={onChange} />
    );

    await user.click(screen.getByRole('combobox', { name: 'workboard.form.execution_mode' }));
    await user.click(
      await screen.findByRole('option', { name: 'workboard.execution_mode.pipeline' })
    );

    expect(onChange).toHaveBeenCalledWith('pipeline');
  });
});

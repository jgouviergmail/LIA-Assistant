/**
 * The priority list (ADR-276, D81): four RANKED marks in the edge's own ink,
 * « any priority » first only where a filter asks for it, and the choice
 * reported as the caller reads it.
 */
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { PRIORITY_ANY, PrioritySelect } from '@/components/workboard/PrioritySelect';

describe('PrioritySelect', () => {
  it('ranks the four levels with a mark in the ink of their edge', async () => {
    const { user } = renderWithProviders(
      <PrioritySelect value="medium" label="Priority" onChange={vi.fn()} />
    );

    await user.click(screen.getByRole('combobox', { name: 'Priority' }));
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual([
      'workboard.priority.low',
      'workboard.priority.medium',
      'workboard.priority.high',
      'workboard.priority.urgent',
    ]);
    expect(options[0].querySelector('.lucide-chevron-down')?.classList).toContain(
      'text-muted-foreground'
    );
    expect(options[1].querySelector('.lucide-minus')?.classList).toContain('text-primary');
    expect(options[2].querySelector('.lucide-chevron-up')?.classList).toContain('text-warning');
    expect(options[3].querySelector('.lucide-chevrons-up')?.classList).toContain(
      'text-destructive'
    );
  });

  it('offers « any » first, under one sign, only when asked', async () => {
    const { user } = renderWithProviders(
      <PrioritySelect withAny value={PRIORITY_ANY} label="Priority" onChange={vi.fn()} />
    );

    expect(screen.getByRole('combobox', { name: 'Priority' })).toHaveTextContent(
      'workboard.filters.priority_any'
    );
    await user.click(screen.getByRole('combobox', { name: 'Priority' }));
    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(5);
    expect(options[0]).toHaveTextContent('workboard.filters.priority_any');
    expect(options[0].querySelector('.lucide-asterisk')).not.toBeNull();
  });

  it('reports the chosen level', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <PrioritySelect value="low" label="Priority" onChange={onChange} />
    );

    await user.click(screen.getByRole('combobox', { name: 'Priority' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.priority.urgent' }));

    expect(onChange).toHaveBeenCalledWith('urgent');
  });
});

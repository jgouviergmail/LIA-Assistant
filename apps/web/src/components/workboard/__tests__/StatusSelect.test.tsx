/**
 * The column list (ADR-276, D17, D79): every column by default, a subset with
 * its exact counts for the phone's picker, and the column header's glyph on
 * each item — the same map, so a header and a list never disagree.
 */
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { StatusSelect } from '@/components/workboard/StatusSelect';
import { TICKET_STATUSES } from '@/types/workboard';

describe('StatusSelect', () => {
  it('offers every column, each wearing its own glyph', async () => {
    const { user } = renderWithProviders(
      <StatusSelect value="todo" label="Column" onChange={vi.fn()} />
    );

    await user.click(screen.getByRole('combobox', { name: 'Column' }));
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual(
      TICKET_STATUSES.map(status => `workboard.columns.${status}`)
    );
    expect(
      screen
        .getByRole('option', { name: 'workboard.columns.done' })
        .querySelector('.lucide-circle-check')
    ).not.toBeNull();
    expect(
      screen
        .getByRole('option', { name: 'workboard.columns.idea' })
        .querySelector('.lucide-lightbulb')
    ).not.toBeNull();
  });

  it('offers only the columns it is given, each with its exact count', async () => {
    // The phone's picker: the columns the board DRAWS, and a count that is an
    // aggregate the server returned (ADR-185), never a page length.
    const { user } = renderWithProviders(
      <StatusSelect
        value="todo"
        label="Column"
        statuses={['todo', 'done']}
        counts={{ todo: 87 }}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('combobox', { name: 'Column' })).toHaveTextContent(
      'workboard.columns.todo (87)'
    );
    await user.click(screen.getByRole('combobox', { name: 'Column' }));
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual([
      'workboard.columns.todo (87)',
      'workboard.columns.done (0)',
    ]);
  });

  it('reports the chosen column', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <StatusSelect value="todo" label="Column" onChange={onChange} />
    );

    await user.click(screen.getByRole('combobox', { name: 'Column' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.columns.waiting' }));

    expect(onChange).toHaveBeenCalledWith('waiting');
  });
});

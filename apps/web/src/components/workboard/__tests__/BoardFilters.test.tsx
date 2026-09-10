/**
 * Narrowing the board.
 *
 * Every control is labelled, its items wear the marks of what they narrow to
 * (D81), and each one produces the filter object the API expects,
 * `undefined` included: an unset filter must cost no query parameter, so
 * « any priority » clears the field rather than sending an empty string —
 * even though Radix makes that entry travel under a sentinel.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { BoardFilters } from '@/components/workboard/BoardFilters';
import type { BoardFilters as Filters } from '@/types/workboard';

const onChange = vi.fn();

function render(filters: Filters = { assignee: 'all', sort: 'position' }) {
  return renderWithProviders(<BoardFilters lng="fr" filters={filters} onChange={onChange} />);
}

beforeEach(() => vi.clearAllMocks());

describe('every control is named', () => {
  it('labels the search, the side, the priority, the sort and the overdue switch', () => {
    render();

    expect(screen.getByLabelText('workboard.filters.search')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'workboard.filters.side' })).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'workboard.filters.priority' })
    ).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'workboard.filters.sort' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'workboard.filters.overdue' })).toBeInTheDocument();
  });

  it('wears a family glyph on every label, the search included', () => {
    render();

    for (const field of ['search', 'side', 'priority', 'sort']) {
      const label = screen.getByText(`workboard.filters.${field}`);
      expect(label.tagName).toBe('LABEL');
      expect(label.querySelector('svg')).not.toBeNull();
    }
  });
});

describe('what each item wears', () => {
  it('marks the sides with the badge glyphs, everyone with the « any » sign', async () => {
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.side' }));

    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual([
      'workboard.filters.side_all',
      'workboard.filters.side_me',
      'workboard.filters.side_lia',
      'workboard.filters.side_peer',
    ]);
    expect(options[0].querySelector('.lucide-asterisk')).not.toBeNull();
    // People in the theme colour (D82), the connection included.
    expect(options[1].querySelector('.lucide-user')?.classList).toContain('text-primary');
    expect(options[2].querySelector('.lucide-sparkles')?.classList).toContain('text-primary');
    expect(options[3].querySelector('.lucide-users')?.classList).toContain('text-primary');
  });

  it('marks « any priority » with the same sign, and the levels with their rank', async () => {
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.priority' }));

    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(5);
    expect(options[0].querySelector('.lucide-asterisk')).not.toBeNull();
    expect(options[4].querySelector('.lucide-chevrons-up')?.classList).toContain(
      'text-destructive'
    );
  });

  it('marks each sort key', async () => {
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.sort' }));

    const due = await screen.findByRole('option', { name: 'workboard.filters.sort_due' });
    expect(due.querySelector('.lucide-calendar-clock')).not.toBeNull();
    expect(
      screen.getByRole('option', { name: 'workboard.filters.sort_position' }).querySelector('svg')
    ).not.toBeNull();
  });
});

describe('what each control produces', () => {
  it('narrows to one side', async () => {
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.side' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.filters.side_lia' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ assignee: 'lia' }));
  });

  it('sends a priority as a LIST', async () => {
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.priority' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.priority.urgent' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ priority: ['urgent'] }));
  });

  it('clears a priority back to undefined, never to an empty list', async () => {
    // `undefined`, never `[]` or `''`: an unset filter must cost no query
    // parameter, so the server keeps its own default.
    const { user } = render({ assignee: 'all', sort: 'position', priority: ['urgent'] });
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.priority' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.filters.priority_any' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ priority: undefined }));
  });

  it('turns the overdue filter on', async () => {
    const { user } = render();
    await user.click(screen.getByRole('checkbox', { name: 'workboard.filters.overdue' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ overdue: true }));
  });

  it('turns the overdue filter back off to undefined', async () => {
    const { user } = render({ assignee: 'all', sort: 'position', overdue: true });
    await user.click(screen.getByRole('checkbox', { name: 'workboard.filters.overdue' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ overdue: undefined }));
  });

  it('changes the sort', async () => {
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.sort' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.filters.sort_due' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ sort: 'due' }));
  });

  it('resets to the board order and every side', async () => {
    const { user } = render({ assignee: 'lia', q: 'salle', overdue: true, sort: 'due' });
    await user.click(screen.getByRole('button', { name: 'workboard.filters.reset' }));

    expect(onChange).toHaveBeenCalledWith({ assignee: 'all', sort: 'position' });
  });
});

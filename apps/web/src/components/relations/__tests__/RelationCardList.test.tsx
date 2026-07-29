/**
 * RelationCardList (N-09) — the CRM overview list.
 *
 * What must hold: empty state when there is nothing; one card per person with
 * their counts; clicking a card opens that person's detail.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { RelationSummary } from '@/hooks/useRelations';

import { RelationCardList } from '../RelationCardList';

function relation(over: Partial<RelationSummary> = {}): RelationSummary {
  return {
    display_name: 'Gérard Dupont',
    identity_confidence: 'exact',
    open_loops_count: 2,
    calls_count: 1,
    last_interaction_at: '2026-07-28T09:00:00Z',
    ...over,
  };
}

describe('RelationCardList', () => {
  it('shows the empty state when there is no relationship', () => {
    renderWithProviders(<RelationCardList relations={[]} onOpen={vi.fn()} />);
    expect(screen.getByText('relations.empty')).toBeInTheDocument();
  });

  it('renders one card per relationship with its counts', () => {
    renderWithProviders(
      <RelationCardList
        relations={[relation(), relation({ display_name: 'Marie', calls_count: 0 })]}
        onOpen={vi.fn()}
      />
    );
    expect(screen.getByText('Gérard Dupont')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
    // Marie has zero calls → no calls chip for her.
    expect(screen.getAllByText(/relations.calls_count/)).toHaveLength(1);
  });

  it('opens the picked relationship', async () => {
    const onOpen = vi.fn();
    const { user } = renderWithProviders(
      <RelationCardList relations={[relation()]} onOpen={onOpen} />
    );
    await user.click(screen.getByRole('button', { name: /Gérard Dupont/ }));
    expect(onOpen).toHaveBeenCalledWith('Gérard Dupont');
  });
});

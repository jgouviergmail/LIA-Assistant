/**
 * RelationCardList (N-09 + favorites) — the CRM overview list.
 *
 * What must hold: empty state when there is nothing; one card per person with
 * their counts; clicking a card opens that person's detail; the star toggles
 * WITHOUT opening; favorites split into their own band; the name filter
 * appears only past the threshold and narrows both bands; the peers badge
 * only shows for connected LIA users.
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
    is_favorite: false,
    is_peer: false,
    ...over,
  };
}

function renderList(
  relations: RelationSummary[],
  over: Partial<{
    onOpen: (name: string) => void;
    onToggleFavorite: (name: string, nextValue: boolean) => void;
  }> = {}
) {
  const onOpen = vi.fn(over.onOpen);
  const onToggleFavorite = vi.fn(over.onToggleFavorite);
  const utils = renderWithProviders(
    <RelationCardList relations={relations} onOpen={onOpen} onToggleFavorite={onToggleFavorite} />
  );
  return { ...utils, onOpen, onToggleFavorite };
}

describe('RelationCardList', () => {
  it('shows the empty state when there is no relationship', () => {
    renderList([]);
    expect(screen.getByText('relations.empty')).toBeInTheDocument();
  });

  it('renders one card per relationship with its counts', () => {
    renderList([relation(), relation({ display_name: 'Marie', calls_count: 0 })]);
    expect(screen.getByText('Gérard Dupont')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
    // Marie has zero calls → no calls chip for her.
    expect(screen.getAllByText(/relations.calls_count/)).toHaveLength(1);
  });

  it('opens the picked relationship', async () => {
    const { user, onOpen } = renderList([relation()]);
    await user.click(screen.getByRole('button', { name: /Gérard Dupont/ }));
    expect(onOpen).toHaveBeenCalledWith('Gérard Dupont');
  });

  it('toggles the star without opening the card', async () => {
    const { user, onOpen, onToggleFavorite } = renderList([relation()]);
    await user.click(screen.getByRole('button', { name: 'relations.favorite_add' }));
    expect(onToggleFavorite).toHaveBeenCalledWith('Gérard Dupont', true);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('unstars a favorite through the same control, pressed state exposed', async () => {
    const { user, onToggleFavorite } = renderList([relation({ is_favorite: true })]);
    const star = screen.getByRole('button', { name: 'relations.favorite_remove' });
    expect(star).toHaveAttribute('aria-pressed', 'true');
    await user.click(star);
    expect(onToggleFavorite).toHaveBeenCalledWith('Gérard Dupont', false);
  });

  it('splits favorites into their own band with counts', () => {
    renderList([
      relation({ display_name: 'Ana', is_favorite: true }),
      relation({ display_name: 'Bob' }),
    ]);
    expect(screen.getByRole('heading', { name: /relations.favorites_title/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /relations.others_title/ })).toBeInTheDocument();
  });

  it('titles the single band as "all" when nothing is starred', () => {
    renderList([relation()]);
    expect(screen.getByRole('heading', { name: /relations.all_title/ })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /relations.favorites_title/ })).toBeNull();
  });

  it('shows the peers badge only for connected LIA users', () => {
    renderList([
      relation({ display_name: 'Ana', is_peer: true }),
      relation({ display_name: 'Bob' }),
    ]);
    expect(screen.getAllByTitle('relations.peer_badge_hint')).toHaveLength(1);
  });

  it('keeps the filter hidden under the threshold', () => {
    renderList([relation()]);
    expect(screen.queryByRole('searchbox')).toBeNull();
  });

  it('filters both bands by name past the threshold', async () => {
    const many = Array.from({ length: 9 }, (_, i) =>
      relation({ display_name: `Person ${i}`, is_favorite: i === 0 })
    );
    const { user } = renderList(many);
    const box = screen.getByRole('searchbox', { name: 'relations.filter_placeholder' });
    await user.type(box, 'Person 3');
    expect(screen.getByText('Person 3')).toBeInTheDocument();
    expect(screen.queryByText('Person 0')).toBeNull();
    // The favorites band vanished with its only (non-matching) member.
    expect(screen.queryByRole('heading', { name: /relations.favorites_title/ })).toBeNull();
  });

  it('says so when the filter matches nobody', async () => {
    const many = Array.from({ length: 9 }, (_, i) => relation({ display_name: `Person ${i}` }));
    const { user } = renderList(many);
    await user.type(
      screen.getByRole('searchbox', { name: 'relations.filter_placeholder' }),
      'zzz'
    );
    expect(screen.getByText('relations.filter_no_match')).toBeInTheDocument();
  });
});

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
    peer_messages_count: 0,
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
    relationsTotal: number;
  }> = {}
) {
  const onOpen = vi.fn(over.onOpen);
  const onToggleFavorite = vi.fn(over.onToggleFavorite);
  const utils = renderWithProviders(
    <RelationCardList
      relations={relations}
      relationsTotal={over.relationsTotal}
      onOpen={onOpen}
      onToggleFavorite={onToggleFavorite}
    />
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

  it('surfaces relayed messages as their own pill', () => {
    renderList([relation({ peer_messages_count: 3 })]);
    expect(screen.getByText('relations.peer_messages_count')).toBeInTheDocument();
  });

  it('hides the messages pill when nothing was exchanged', () => {
    renderList([relation({ peer_messages_count: 0 })]);
    expect(screen.queryByText('relations.peer_messages_count')).toBeNull();
  });

  it('still renders the pills row for a message-only relationship', () => {
    // A connected peer with no loop and no call had NO card at all before the
    // bridge — the row must not stay hidden just because the other two are 0.
    renderList([relation({ open_loops_count: 0, calls_count: 0, peer_messages_count: 2 })]);
    expect(screen.getByText('relations.peer_messages_count')).toBeInTheDocument();
    expect(screen.queryByText('relations.open_loops_count')).toBeNull();
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
    await user.type(screen.getByRole('searchbox', { name: 'relations.filter_placeholder' }), 'zzz');
    expect(screen.getByText('relations.filter_no_match')).toBeInTheDocument();
  });
});

describe('RelationCardList — dormancy, ordering and quick filters', () => {
  const RECENT = new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString();
  const OLD = new Date(Date.now() - 200 * 24 * 3600 * 1000).toISOString();

  /** Enough people to bring the toolbar out (it hides under the threshold). */
  const many = (over: Partial<RelationSummary>[] = []) => [
    ...over.map((patch, index) => relation({ display_name: `P${index}`, ...patch })),
    ...Array.from({ length: 9 }, (_, index) =>
      relation({ display_name: `Filler ${index}`, last_interaction_at: RECENT })
    ),
  ];

  it('flags a relationship that has been silent for a quarter', () => {
    renderList([
      relation({ display_name: 'Ancienne', last_interaction_at: OLD }),
      relation({ display_name: 'Fraîche', last_interaction_at: RECENT }),
    ]);
    expect(screen.getAllByText('relations.dormant')).toHaveLength(1);
  });

  it('never flags someone with no signal at all as dormant', () => {
    // "No recent signal" and "gone quiet" are different statements — a
    // starred person with no history was never active to begin with.
    renderList([relation({ last_interaction_at: null })]);
    expect(screen.queryByText('relations.dormant')).toBeNull();
    expect(screen.getByText('relations.no_recent_signal')).toBeInTheDocument();
  });

  it('keeps the toolbar hidden under the threshold', () => {
    renderList([relation()]);
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('narrows to connected LIA users on demand', async () => {
    const { user } = renderList(
      many([
        { display_name: 'Peer', is_peer: true, last_interaction_at: RECENT },
        { display_name: 'Autre', is_peer: false, last_interaction_at: RECENT },
      ])
    );
    const chip = screen.getByRole('button', { name: 'relations.only_peers' });
    expect(chip).toHaveAttribute('aria-pressed', 'false');

    await user.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Peer')).toBeInTheDocument();
    expect(screen.queryByText('Autre')).toBeNull();
    expect(screen.queryByText('Filler 0')).toBeNull();
  });

  it('narrows to dormant relationships on demand', async () => {
    const { user } = renderList(
      many([
        { display_name: 'Endormie', last_interaction_at: OLD },
        { display_name: 'Active', last_interaction_at: RECENT },
      ])
    );
    await user.click(screen.getByRole('button', { name: 'relations.only_dormant' }));
    expect(screen.getByText('Endormie')).toBeInTheDocument();
    expect(screen.queryByText('Active')).toBeNull();
  });

  /** Rank of a person in the rendered list (the avatar prefixes initials, so
   *  the oracle is containment and RELATIVE order, never a string prefix). */
  const rankOf = (name: string) =>
    screen.getAllByRole('listitem').findIndex(item => (item.textContent ?? '').includes(name));

  it('reorders by name without refetching', async () => {
    const { user, onOpen } = renderList(
      many([
        { display_name: 'Zoé', last_interaction_at: RECENT },
        { display_name: 'Alice', last_interaction_at: RECENT },
      ])
    );
    expect(rankOf('Zoé')).toBeLessThan(rankOf('Alice')); // server ranking kept

    await user.selectOptions(screen.getByRole('combobox'), 'name');
    expect(rankOf('Alice')).toBeLessThan(rankOf('Zoé'));
    // A display preference is not worth a refetch, nor an accidental open.
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('reorders by activity volume', async () => {
    const { user } = renderList(
      many([
        { display_name: 'Calme', open_loops_count: 0, calls_count: 0, peer_messages_count: 0 },
        { display_name: 'Intense', open_loops_count: 5, calls_count: 4, peer_messages_count: 3 },
      ])
    );
    expect(rankOf('Calme')).toBeLessThan(rankOf('Intense')); // server ranking kept

    await user.selectOptions(screen.getByRole('combobox'), 'volume');
    expect(rankOf('Intense')).toBeLessThan(rankOf('Calme'));
  });

  it('says so when the combined filters match nobody', async () => {
    const { user } = renderList(many([{ display_name: 'Active', last_interaction_at: RECENT }]));
    await user.click(screen.getByRole('button', { name: 'relations.only_dormant' }));
    expect(screen.getByText('relations.filter_no_match')).toBeInTheDocument();
  });

  describe('the server-side cap', () => {
    it('states what the page left out instead of dropping people in silence', () => {
      renderList([relation()], { relationsTotal: 34 });
      expect(screen.getByText('relations.more_not_shown')).toBeInTheDocument();
    });

    it('says nothing when the page holds everything', () => {
      renderList([relation()], { relationsTotal: 1 });
      expect(screen.queryByText('relations.more_not_shown')).toBeNull();
    });

    it('keeps warning while the user filters — a filter over a capped set can lie', async () => {
      // "No match" is only trustworthy if the filter saw everything. It did
      // not: the server already dropped rows, so the warning matters MORE
      // here, not less. It is counted against the whole page, never against
      // the filtered view (which the user chose and can undo).
      const { user } = renderList(many(), { relationsTotal: 40 });
      await user.type(screen.getByRole('searchbox'), 'zzz');
      expect(screen.getByText('relations.filter_no_match')).toBeInTheDocument();
      // "Nobody matches" next to "30 more are not shown" — the second is what
      // stops the first from being read as a fact about the whole address book.
      expect(screen.getByText('relations.more_not_shown')).toBeInTheDocument();
    });
  });
});

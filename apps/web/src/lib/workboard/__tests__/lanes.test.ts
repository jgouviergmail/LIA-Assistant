/**
 * The board's lanes, as a pure model.
 *
 * A lane is a category; the board draws one row per lane and a ticket filed
 * under nothing sits in the unfiled one. Every case below is a way the lanes
 * could lie or lose something: an empty lane hidden while nothing narrows the
 * board (where would a card be dropped?), a ticket vanishing because its
 * category was deleted a second ago, a peer offered a lane the server will
 * refuse, a stripe pattern that breaks when a lane is hidden.
 */
import { describe, it, expect } from 'vitest';

import { makeTicket } from '@/__tests__/factories';
import {
  UNFILED_LANE,
  canFile,
  categoryOfLaneKey,
  laneKey,
  laneOf,
  categoryNamer,
  knownCategories,
  laneOptions,
  lanePatch,
  laneViews,
  ownCategories,
  ticketsOfCell,
} from '@/lib/workboard/lanes';
import type { LaneRow } from '@/types/workboard';

const ME = 'me';
const PEER = 'peer';

function lane(
  category_id: string | null,
  counts: Record<string, number> = {},
  owner_user_id: string | null = category_id === null ? null : ME
): LaneRow {
  return {
    category_id,
    name: category_id === null ? null : `Name of ${category_id}`,
    owner_user_id,
    counts_by_status: { idea: 0, todo: 0, done: 0, ...counts },
  };
}

describe('laneViews', () => {
  it('draws nothing for a reader with no category in sight', () => {
    expect(laneViews([], ME, false)).toEqual([]);
  });

  it('keeps the order the server gave and sums each lane exactly', () => {
    const views = laneViews(
      [lane(null, { todo: 2 }), lane('home', { todo: 1, done: 3 }), lane('work')],
      ME,
      false
    );
    expect(views.map(view => view.key)).toEqual([UNFILED_LANE, 'home', 'work']);
    expect(views.map(view => view.total)).toEqual([2, 4, 0]);
  });

  it('keeps an empty lane while nothing narrows the board — it is where a card is dropped', () => {
    const views = laneViews([lane(null), lane('home')], ME, false);
    expect(views.map(view => view.key)).toEqual([UNFILED_LANE, 'home']);
  });

  it('hides the lanes a filter left empty, and says so by not drawing them', () => {
    const views = laneViews([lane(null), lane('home', { todo: 1 }), lane('work')], ME, true);
    expect(views.map(view => view.key)).toEqual(['home']);
  });

  it('numbers the stripes over the lanes DRAWN, so the grounds keep alternating', () => {
    const views = laneViews(
      [lane(null), lane('a', { todo: 1 }), lane('b'), lane('c', { todo: 1 })],
      ME,
      true
    );
    expect(views.map(view => [view.key, view.stripe])).toEqual([
      ['a', 0],
      ['c', 1],
    ]);
  });

  it('marks the unfiled lane and the reader’s own as theirs, and nobody else’s', () => {
    const views = laneViews([lane(null), lane('home'), lane('shared', {}, PEER)], ME, false);
    expect(views.map(view => view.mine)).toEqual([true, true, false]);
  });
});

describe('lane keys', () => {
  it('round-trips a category and the unfiled lane', () => {
    expect(categoryOfLaneKey(laneKey('home'))).toBe('home');
    expect(categoryOfLaneKey(laneKey(null))).toBeNull();
  });
});

describe('laneOf', () => {
  const known = new Set(['home']);

  it('reads the category the ticket is filed under', () => {
    expect(laneOf(makeTicket({ category_id: 'home' }), known)).toBe('home');
    expect(laneOf(makeTicket({ category_id: null }), known)).toBeNull();
  });

  it('sends a ticket whose category is not on the board to the unfiled lane', () => {
    // The category was deleted a moment ago and the page has not been read
    // again yet: the card must stay on screen, never fall between two lanes.
    expect(laneOf(makeTicket({ category_id: 'gone' }), known)).toBeNull();
  });
});

describe('ticketsOfCell', () => {
  const known = new Set(['home']);
  const column = [
    makeTicket({ id: 'a', category_id: 'home' }),
    makeTicket({ id: 'b', category_id: null }),
    makeTicket({ id: 'c', category_id: 'home' }),
    makeTicket({ id: 'd', category_id: 'gone' }),
  ];

  it('keeps the column’s own order inside a lane', () => {
    expect(ticketsOfCell(column, 'home', known).map(row => row.id)).toEqual(['a', 'c']);
  });

  it('gathers the unfiled and the orphaned in the unfiled lane', () => {
    expect(ticketsOfCell(column, null, known).map(row => row.id)).toEqual(['b', 'd']);
  });
});

describe('canFile', () => {
  const mine = { categoryId: 'home', mine: true };
  const unfiled = { categoryId: null, mine: true };
  const theirs = { categoryId: 'shared', mine: false };

  it('lets the owner file a ticket under their own lanes or under nothing', () => {
    expect(canFile(null, true, mine)).toBe(true);
    expect(canFile('home', true, unfiled)).toBe(true);
  });

  it('never offers somebody else’s lane, even to the owner of the ticket', () => {
    expect(canFile(null, true, theirs)).toBe(false);
  });

  it('lets a holder move a ticket inside its own lane and nowhere else', () => {
    expect(canFile('shared', false, theirs)).toBe(true);
    expect(canFile('shared', false, mine)).toBe(false);
    expect(canFile('shared', false, unfiled)).toBe(false);
  });

  it('lets a holder move an unfiled ticket inside the unfiled lane', () => {
    expect(canFile(null, false, unfiled)).toBe(true);
    expect(canFile(null, false, mine)).toBe(false);
  });
});

describe('lanePatch', () => {
  it('names the category, or says to clear it — never a null the API reads as « unchanged »', () => {
    expect(lanePatch('home')).toEqual({ category_id: 'home' });
    expect(lanePatch(null)).toEqual({ clear_category: true });
  });
});

describe('knownCategories', () => {
  it('holds the categories of the lanes DRAWN, and never the unfiled lane', () => {
    const drawn = laneViews(
      [lane(null, { todo: 1 }), lane('home', { todo: 1 }), lane('work')],
      ME,
      true
    );
    // `work` is empty under a filter: it is not drawn, so a card filed there
    // has no lane on screen and falls in the unfiled one.
    expect([...knownCategories(drawn)]).toEqual(['home']);
  });
});

describe('what the lanes say of the categories', () => {
  // The board's own payload names every category in sight, so the lists that
  // offer them read it rather than asking the server a second time.
  const lanes = [
    lane(null, { todo: 1 }),
    lane('home', { todo: 2 }),
    lane('work'),
    lane('shared', { todo: 1 }, PEER),
  ];

  it('gives the reader’s OWN categories, in order — the lanes their tickets may be filed under', () => {
    expect(ownCategories(lanes, ME)).toEqual([
      { id: 'home', name: 'Name of home' },
      { id: 'work', name: 'Name of work' },
    ]);
  });

  it('gives nobody’s categories to a reader it cannot identify', () => {
    expect(ownCategories(lanes, undefined)).toEqual([]);
  });

  it('offers every category to narrow to, and says whose somebody else’s is', () => {
    const ownerName = (userId: string) => (userId === PEER ? 'Marie' : 'someone');
    expect(laneOptions(lanes, ME, ownerName)).toEqual([
      { id: 'home', name: 'Name of home' },
      { id: 'work', name: 'Name of work' },
      { id: 'shared', name: 'Name of shared · Marie' },
    ]);
  });

  it('names a category of the board, and nothing else', () => {
    const nameOf = categoryNamer(lanes);
    expect(nameOf('shared')).toBe('Name of shared');
    expect(nameOf('gone')).toBeUndefined();
  });
});

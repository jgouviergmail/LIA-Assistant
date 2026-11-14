/**
 * The board in lanes, in a real browser (ADR-276 amendment 2026-11-11).
 *
 * A category is a lane of the board. What only a laid-out, hit-tested page
 * can prove — and what each case below measures rather than reads off a class:
 *
 * 1. **The grounds alternate and a card never wears its lane's.** Lanes are
 *    told apart by a ground, never by a colour per category; the colours are
 *    read back computed, in light, dark and OLED.
 * 2. **The column names stay in sight.** The board is its own scroll region in
 *    both directions, and the page body never scrolls sideways.
 * 3. **A drag is ONE write.** A card dropped in another lane of another column
 *    asks the server for the column, the place and the category together;
 *    with the pointer and with the keyboard.
 * 4. **The category is the owner's.** A ticket held for somebody else stays in
 *    their lane: the other lanes close while it is in the air, and a drop on
 *    one of them writes nothing.
 * 5. **On a phone nothing drags**: one column, grouped by lane, each lane's
 *    name pinned while its cards scroll, and the category a list on the card.
 * 6. **The whole board's figures stand above the filters** (owner, 2026-11-11:
 *    they were a settings section). A figure narrows the board in place; the
 *    block is open on a computer, folded on a phone, and folded it asks the
 *    server nothing.
 * 7. **A hairline marks each column off the one before it**, at the same place
 *    under the column names and in every lane — measured, not read off a class.
 *
 * The oracle for every write is what is ASKED of the server — the one thing
 * that survives a refactor of the gesture.
 */
import type { Page, Route } from '@playwright/test';

import { scanPage } from '../a11y/scan';
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { expectNoZoomOnFocus } from './phone-lines';

/** The id the auth fixture signs in with. */
const ME = '00000000-0000-4000-8000-000000000001';
const MARIE = '00000000-0000-4000-8000-0000000000a1';
const HOME = '11111111-1111-4111-8111-111111111111';
const WORK = '22222222-2222-4222-8222-222222222222';
const SITE = '33333333-3333-4333-8333-333333333333';

const CARD = '[data-testid="ticket-card"]';
const STATUSES = ['idea', 'todo', 'in_progress', 'waiting', 'confirming', 'validating', 'done'];

interface Ticket {
  id: string;
  owner_user_id: string;
  title: string;
  status: string;
  position: number;
  category_id: string | null;
  [field: string]: unknown;
}

interface Category {
  id: string;
  owner_user_id: string;
  name: string;
  position: number;
}

function ticket(index: number, over: Partial<Ticket>): Ticket {
  return {
    id: `8f0e1d2c-1111-4000-8000-${String(index).padStart(12, '0')}`,
    owner_user_id: ME,
    parent_id: null,
    category_id: null,
    title: `Ticket ${index}`,
    description: null,
    status: 'todo',
    priority: 'medium',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: ME,
    position: 0,
    follow_owner: false,
    follow_assignee: false,
    created_by: 'user',
    execution_mode: 'react',
    status_changed_at: '2026-11-10T10:00:00Z',
    run_count: 0,
    run_claimed_at: null,
    last_run_at: null,
    last_run_outcome: null,
    last_run_error: null,
    last_run_tokens_in: null,
    last_run_tokens_out: null,
    last_run_tokens_cache: null,
    last_run_google_requests: null,
    last_run_cost_eur: null,
    total_tokens_in: 0,
    total_tokens_out: 0,
    total_tokens_cache: 0,
    total_google_requests: 0,
    total_cost_eur: 0,
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    ...over,
  };
}

/**
 * A board the mocks keep in memory, answering like the service: one order per
 * column, exact counts per lane, a deleted category releasing its tickets.
 */
function boardWorld(tickets: Ticket[], categories: Category[]) {
  const world = {
    tickets,
    categories,
    /** Every body asked of `POST /tickets/{id}/move`, in order. */
    moves: [] as Record<string, unknown>[],
    /** Every body asked of `PATCH /tickets/{id}`. */
    patches: [] as Record<string, unknown>[],
    /** Every write asked of the categories, as `METHOD body-or-id`. */
    categoryWrites: [] as { method: string; id?: string; body?: Record<string, unknown> }[],
    /** The query of every `GET /tickets`, in order — what the filters asked for. */
    reads: [] as string[],
    /** How many times the whole board's figures were asked for. */
    summaryReads: 0,
  };

  const column = (status: string) =>
    world.tickets.filter(row => row.status === status).sort((a, b) => a.position - b.position);
  const visibleCategories = () =>
    [...world.categories].sort(
      (a, b) =>
        Number(a.owner_user_id !== ME) - Number(b.owner_user_id !== ME) || a.position - b.position
    );
  const countsOf = (rows: Ticket[]) => {
    const counts: Record<string, number> = {};
    for (const status of STATUSES) counts[status] = 0;
    for (const row of rows) counts[row.status] += 1;
    return counts;
  };
  const boardPage = () => ({
    tickets: STATUSES.flatMap(column),
    total: world.tickets.length,
    counts_by_status: countsOf(world.tickets),
    lanes:
      world.categories.length === 0
        ? []
        : [
            {
              category_id: null,
              name: null,
              owner_user_id: null,
              counts_by_status: countsOf(world.tickets.filter(row => row.category_id === null)),
            },
            ...visibleCategories().map(category => ({
              category_id: category.id,
              name: category.name,
              owner_user_id: category.owner_user_id,
              counts_by_status: countsOf(
                world.tickets.filter(row => row.category_id === category.id)
              ),
            })),
          ],
  });
  const renumber = (status: string, rows: Ticket[]) =>
    rows.forEach((row, index) => {
      row.status = status;
      row.position = index;
    });
  const file = (row: Ticket, body: Record<string, unknown>) => {
    if (body.clear_category === true) row.category_id = null;
    else if (typeof body.category_id === 'string') row.category_id = body.category_id;
  };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  const idOf = (route: Route, tail = '') => {
    const match = new RegExp(`/([0-9a-f-]{36})${tail}$`).exec(
      new URL(route.request().url()).pathname
    );
    return match ? match[1] : '';
  };

  const routes: MockRoute[] = [
    { url: '**/api/v1/notifications/hub-counts', json: { workboard: 0 } },
    {
      url: '**/api/v1/peers/connections',
      json: [
        {
          id: '00000000-0000-4000-8000-0000000000c1',
          peer_id: MARIE,
          peer_display_name: 'Marie',
          peer_email_hint: 'm***@example.org',
          peer_email: null,
          status: 'accepted',
          direction: 'outgoing',
          requested_at: '2026-11-01T10:00:00Z',
          responded_at: '2026-11-01T11:00:00Z',
          context_message: null,
          my_shares: [],
          their_shares: [],
        },
      ],
    },
    {
      url: /\/api\/v1\/workboard\/tickets(\?.*)?$/,
      method: 'GET',
      handler: route => {
        world.reads.push(new URL(route.request().url()).search);
        return json(route, boardPage());
      },
    },
    {
      // The whole board at a glance: aggregates over every ticket, whatever
      // the filters of the page under it.
      url: /\/api\/v1\/workboard\/summary$/,
      method: 'GET',
      handler: route => {
        world.summaryReads += 1;
        const whole = boardPage();
        return json(route, {
          total: whole.total,
          counts_by_status: whole.counts_by_status,
          overdue: 0,
          held_by_lia: 0,
          held_by_me: world.tickets.filter(row => row.effective_assignee_id === ME).length,
          needs_me: 0,
          owned: world.tickets.filter(row => row.owner_user_id === ME).length,
          max_tickets: 200,
          max_runs_per_ticket: 10,
          runs_total: 0,
          tokens_in: 0,
          tokens_out: 0,
          tokens_cache: 0,
          google_requests: 0,
          cost_eur: 0,
          lanes: whole.lanes,
        });
      },
    },
    {
      url: /\/api\/v1\/workboard\/tickets\/[0-9a-f-]{36}\/move$/,
      method: 'POST',
      handler: route => {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        world.moves.push(body);
        const row = world.tickets.find(candidate => candidate.id === idOf(route, '/move'));
        if (!row) return json(route, { detail: 'workboard_not_found' }, 404);
        const from = row.status;
        const target = column(String(body.status)).filter(other => other.id !== row.id);
        target.splice(Number(body.position), 0, row);
        row.status = String(body.status);
        renumber(row.status, target);
        if (from !== row.status) renumber(from, column(from));
        file(row, body);
        return json(route, row);
      },
    },
    {
      url: /\/api\/v1\/workboard\/tickets\/[0-9a-f-]{36}$/,
      method: 'PATCH',
      handler: route => {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        world.patches.push(body);
        const row = world.tickets.find(candidate => candidate.id === idOf(route));
        if (!row) return json(route, { detail: 'workboard_not_found' }, 404);
        file(row, body);
        return json(route, row);
      },
    },
    {
      url: /\/api\/v1\/workboard\/tickets\/[0-9a-f-]{36}$/,
      method: 'GET',
      handler: route =>
        json(route, {
          ticket: world.tickets.find(candidate => candidate.id === idOf(route)),
          children: [],
          comments: [],
          events: [],
        }),
    },
    {
      url: /\/api\/v1\/workboard\/categories$/,
      method: 'GET',
      handler: route =>
        json(route, {
          categories: visibleCategories().map(category => ({
            ...category,
            ticket_count: world.tickets.filter(row => row.category_id === category.id).length,
          })),
          max_categories: 20,
          name_max_chars: 40,
        }),
    },
    {
      url: /\/api\/v1\/workboard\/categories$/,
      method: 'POST',
      handler: route => {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        world.categoryWrites.push({ method: 'POST', body });
        const created: Category = {
          id: `44444444-4444-4444-8444-${String(world.categories.length).padStart(12, '0')}`,
          owner_user_id: ME,
          name: String(body.name),
          position: world.categories.filter(category => category.owner_user_id === ME).length,
        };
        world.categories.push(created);
        return json(route, { ...created, ticket_count: 0 }, 201);
      },
    },
    {
      url: /\/api\/v1\/workboard\/categories\/[0-9a-f-]{36}$/,
      method: 'PATCH',
      handler: route => {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        const id = idOf(route);
        world.categoryWrites.push({ method: 'PATCH', id, body });
        const mine = world.categories
          .filter(category => category.owner_user_id === ME)
          .sort((a, b) => a.position - b.position);
        const moved = mine.find(category => category.id === id);
        if (!moved) return json(route, { detail: 'not_found' }, 404);
        if (typeof body.name === 'string') moved.name = body.name;
        if (typeof body.position === 'number') {
          const rest = mine.filter(category => category.id !== id);
          rest.splice(body.position, 0, moved);
          rest.forEach((category, index) => (category.position = index));
        }
        return json(route, { ...moved, ticket_count: 0 });
      },
    },
    {
      url: /\/api\/v1\/workboard\/categories\/[0-9a-f-]{36}$/,
      method: 'DELETE',
      handler: route => {
        const id = idOf(route);
        world.categoryWrites.push({ method: 'DELETE', id });
        const released = world.tickets.filter(row => row.category_id === id);
        released.forEach(row => (row.category_id = null));
        world.categories = world.categories.filter(category => category.id !== id);
        world.categories
          .filter(category => category.owner_user_id === ME)
          .sort((a, b) => a.position - b.position)
          .forEach((category, index) => (category.position = index));
        return json(route, { released: released.length });
      },
    },
  ];
  return { world, routes };
}

/**
 * The reader's board: two categories of their own (« Travail » holds nothing),
 * one of Marie's for the ticket they hold for her, and one ticket not filed.
 */
function standardWorld() {
  return boardWorld(
    [
      ticket(1, { title: 'À trier', position: 0 }),
      ticket(2, { title: 'Repeindre le salon', position: 1, category_id: HOME }),
      ticket(3, { title: 'Appeler le plombier', position: 2, category_id: HOME }),
      ticket(4, {
        title: 'Relire le devis',
        position: 3,
        category_id: SITE,
        owner_user_id: MARIE,
        assignee_user_id: ME,
      }),
      ticket(5, { title: 'Poncer la porte', status: 'done', position: 0, category_id: HOME }),
    ],
    [
      { id: HOME, owner_user_id: ME, name: 'Maison', position: 0 },
      { id: WORK, owner_user_id: ME, name: 'Travail', position: 1 },
      { id: SITE, owner_user_id: MARIE, name: 'Chantier', position: 0 },
    ]
  );
}

/** The lanes, read inside the board: the page has other regions (the filters). */
const lanes = (page: Page) =>
  page
    .getByRole('group', { name: 'Tableau des tickets, un couloir par catégorie' })
    .getByRole('region');
const lane = (page: Page, key: string) => page.getByTestId(`lane-${key}`);
const cell = (page: Page, key: string, status: string) => page.getByTestId(`cell-${key}-${status}`);
const card = (page: Page, title: string) => page.locator(CARD).filter({ hasText: title });
/** The whole board's figures, above the filters. */
const glance = (page: Page) =>
  // Whichever apostrophe the locale writes: the title is matched around it.
  page.locator('details').filter({ hasText: /Le tableau en un coup d.œil/ });

/** Drag with the pointer, in steps: the sensor needs travel before it picks a card up. */
async function drag(page: Page, from: { x: number; y: number }, to: { x: number; y: number }) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 12, from.y + 12, { steps: 4 });
  await page.mouse.move(to.x, to.y, { steps: 12 });
  // One more move on the target: the collision is read on pointer movement.
  await page.mouse.move(to.x + 1, to.y + 1);
}

async function centre(page: Page, target: ReturnType<Page['locator']>) {
  const box = await target.boundingBox();
  if (!box) throw new Error('not drawn');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/**
 * Where a hand takes a card: its bottom right corner, clear of its controls.
 *
 * The title is the door that OPENS the ticket and deliberately keeps the
 * pointer from the drag listeners, so a press on it is never a drag — which is
 * exactly what the centre of a card is.
 */
async function grip(page: Page, title: string) {
  const box = await card(page, title).boundingBox();
  if (!box) throw new Error('not drawn');
  return { x: box.x + box.width - 28, y: box.y + box.height - 10 };
}

/**
 * Let the keyboard sensor hear the next key.
 *
 * dnd-kit picks a card up on « Space » and attaches the listener for the keys
 * that follow ONE TASK LATER. A key sent before that task ran is lost, and the
 * card stays where it was — a race a hand never wins and a script sometimes
 * does. A timer queued now runs after the sensor's own, queued at the pick-up.
 */
async function sensorListening(page: Page) {
  await page.evaluate(() => new Promise<void>(resolve => setTimeout(resolve, 0)));
}

/** Bring the whole board into view, so no box is read before a scroll moves it. */
async function settleBoard(page: Page) {
  await page.getByTestId('lane-board').evaluate(node => node.scrollIntoView({ block: 'start' }));
}

async function open(page: Page) {
  await page.goto('/fr/dashboard/workboard');
  await waitForHydration(page, CARD);
}

test.describe('the workboard in lanes — from lg up', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('draws one lane per category and alternates the grounds in every theme', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(standardWorld().routes);
    await open(page);

    await expect(lanes(page)).toHaveCount(4);
    await expect(lanes(page).first()).toHaveAccessibleName('Couloir À catégoriser');
    await expect(lane(page, HOME)).toContainText('Repeindre le salon');
    await expect(lane(page, HOME)).not.toContainText('À trier');
    await expect(cell(page, HOME, 'done')).toContainText('Poncer la porte');
    // Somebody else's lane says whose it is.
    await expect(lane(page, SITE).locator('header')).toContainText('De Marie');
    // An empty lane is its header alone.
    await expect(lane(page, WORK).locator('[data-testid^="cell-"]')).toHaveCount(0);

    for (const theme of ['light', 'dark', 'oled']) {
      await page.evaluate(value => {
        document.documentElement.classList.toggle('dark', value !== 'light');
        document.documentElement.toggleAttribute('data-oled', value === 'oled');
      }, theme);
      const grounds = await page.evaluate(selector => {
        const lanes = [...document.querySelectorAll<HTMLElement>('[data-testid^="lane-"]')].filter(
          node => node.tagName === 'SECTION'
        );
        return lanes.map(node => ({
          lane: getComputedStyle(node).backgroundColor,
          cards: [...node.querySelectorAll<HTMLElement>(selector)].map(
            item => getComputedStyle(item).backgroundColor
          ),
        }));
      }, CARD);
      expect(grounds, theme).toHaveLength(4);
      for (let index = 0; index < grounds.length; index += 1) {
        // Two neighbours never share a ground…
        if (index > 0) expect(grounds[index].lane, theme).not.toBe(grounds[index - 1].lane);
        // …and a card never wears the ground it sits on.
        for (const ground of grounds[index].cards) {
          expect(ground, theme).not.toBe(grounds[index].lane);
        }
      }
      // Two grounds in all, whole: the third lane is the first one's again.
      expect(grounds[2].lane, theme).toBe(grounds[0].lane);
    }
  });

  test('marks each column off the one before it with a hairline, under the names and in every lane', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(standardWorld().routes);
    await open(page);
    await settleBoard(page);

    const drawn = await page.evaluate(home => {
      const box = (node: Element) => node.getBoundingClientRect();
      const rule = (node: Element) => {
        const line = node.querySelector('[data-column-rule]');
        if (!line) return null;
        const { left, width, bottom } = box(line);
        return { left, width, bottom, colour: getComputedStyle(line).backgroundColor };
      };
      const names = [...document.querySelectorAll('[data-testid^="column-header-"]')];
      const lane = document.querySelector(`[data-testid="lane-${home}"]`)!;
      const cells = [...lane.querySelectorAll('[data-testid^="cell-"]')];
      const frame = document.querySelector('[data-testid="lane-board"]')!;
      return {
        cells: cells.map(node => ({ left: box(node).left, right: box(node).right })),
        cellRules: cells.map(rule),
        nameRules: names.map(rule),
        nameRowBottom: box(names[0].parentElement!).bottom,
        laneBottom: box(lane).bottom,
        line: getComputedStyle(frame).borderTopColor,
      };
    }, HOME);

    // Six columns drawn (« À confirmer » holds nothing): five boundaries.
    expect(drawn.cells).toHaveLength(6);
    expect(drawn.cellRules[0]).toBeNull();
    expect(drawn.nameRules[0]).toBeNull();
    for (let index = 1; index < drawn.cells.length; index += 1) {
      const inLane = drawn.cellRules[index]!;
      const underNames = drawn.nameRules[index]!;
      const gap = { from: drawn.cells[index - 1].right, to: drawn.cells[index].left };
      // A hairline, in the neutral line colour every panel edge draws.
      expect(inLane.width, `column ${index}`).toBe(1);
      expect(inLane.colour, `column ${index}`).toBe(drawn.line);
      // In the gap, at its middle — never over a card.
      expect(inLane.left, `column ${index}`).toBeGreaterThan(gap.from);
      expect(inLane.left + inLane.width, `column ${index}`).toBeLessThan(gap.to);
      expect(Math.abs(inLane.left + 0.5 - (gap.from + gap.to) / 2), `column ${index}`).toBeLessThan(
        1
      );
      // The names' row is ruled at the SAME place, down to the line under it…
      expect(Math.abs(underNames.left - inLane.left), `column ${index}`).toBeLessThan(0.6);
      expect(Math.abs(underNames.bottom - drawn.nameRowBottom), `column ${index}`).toBeLessThan(
        1.6
      );
      // …and a lane's rule runs to the lane's own bottom line.
      expect(Math.abs(inLane.bottom - drawn.laneBottom), `column ${index}`).toBeLessThan(1.6);
    }
  });

  test('shows the whole board at a glance above the filters, and a figure narrows the board in place', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);

    // Open on arrival where the screen has room, and ABOVE the filters.
    await expect(glance(page)).toHaveAttribute('open', '');
    // Arriving open is nobody's choice: a browser fires « toggle » on a block
    // created open, and that must not be remembered as one.
    const remembered = () =>
      page.evaluate(
        () =>
          (JSON.parse(localStorage.getItem('lia_workboard_lanes_prefs') ?? '{}').state
            ?.summaryOpen as boolean | null | undefined) ?? null
      );
    expect(await remembered()).toBeNull();
    const total = glance(page).getByRole('button', { name: /Sur ton tableau/ });
    await expect(total).toContainText('5');
    const panel = (await glance(page).boundingBox())!;
    const filters = (await page.getByLabel('Chercher un titre').boundingBox())!;
    expect(panel.y + panel.height).toBeLessThanOrEqual(filters.y);

    // A lane's figure counts the whole lane, and narrows the board to it.
    const home = glance(page).getByRole('button', { name: /Maison/ });
    await expect(home).toContainText('3');
    await home.click();
    await expect.poll(() => world.reads.at(-1) ?? '').toContain(`category=${HOME}`);
    await expect(page).toHaveURL(new RegExp(`category=${HOME}`));
    // « Sur ton tableau » is the whole board again.
    await total.click();
    await expect.poll(() => world.reads.at(-1) ?? '').not.toContain('category=');

    // A write on the page moves the figures: they are read again.
    await settleBoard(page);
    const before = world.summaryReads;
    await drag(page, await grip(page, 'À trier'), await centre(page, cell(page, HOME, 'in_progress')));
    await page.mouse.up();
    await expect.poll(() => world.moves.length).toBe(1);
    await expect.poll(() => world.summaryReads).toBeGreaterThan(before);
    await expect(glance(page).getByRole('button', { name: /Maison/ })).toContainText('4');

    // Folded by the person, it stays folded on this device.
    await glance(page).locator('summary').click();
    await expect(glance(page)).not.toHaveAttribute('open', '');
    // Polled: the block closes natively, and the « toggle » that records the
    // choice is dispatched a task later.
    await expect.poll(remembered).toBe(false);
    await page.reload();
    await waitForHydration(page, CARD);
    await expect(glance(page)).not.toHaveAttribute('open', '');
  });

  test('keeps the column names in sight and the page body still', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Enough cards for the board to be taller than its region, at a width
    // where six columns do not fit.
    const crowd = Array.from({ length: 14 }, (_, index) =>
      ticket(index + 10, { title: `Carte ${index}`, position: index, category_id: HOME })
    );
    const { routes } = boardWorld(
      [...crowd, ticket(1, { title: 'À trier', position: 14 })],
      [
        { id: HOME, owner_user_id: ME, name: 'Maison', position: 0 },
        { id: WORK, owner_user_id: ME, name: 'Travail', position: 1 },
      ]
    );
    await page.setViewportSize({ width: 1024, height: 700 });
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);

    const region = page.getByTestId('lane-board');
    const header = page.getByTestId('column-header-todo');
    await region.scrollIntoViewIfNeeded();
    await region.evaluate(node => node.scrollIntoView({ block: 'start' }));
    const measure = () =>
      page.evaluate(() => {
        const board = document.querySelector<HTMLElement>('[data-testid="lane-board"]')!;
        const names = document.querySelector<HTMLElement>('[data-testid="column-header-todo"]')!
          .parentElement!;
        const laneName = document.querySelector<HTMLElement>(
          '[data-testid^="lane-"] header h3'
        )!;
        return {
          boardTop: board.getBoundingClientRect().top,
          boardLeft: board.getBoundingClientRect().left,
          namesTop: names.getBoundingClientRect().top,
          laneNameLeft: laneName.getBoundingClientRect().left,
          scrollable: board.scrollHeight - board.clientHeight,
          sideways: board.scrollWidth - board.clientWidth,
          bodyOverflow:
            document.documentElement.scrollWidth - document.documentElement.clientWidth,
        };
      });

    const before = await measure();
    expect(before.scrollable).toBeGreaterThan(200);
    expect(before.sideways).toBeGreaterThan(50);
    // Six columns do not fit: the REGION scrolls sideways, never the page.
    expect(before.bodyOverflow).toBeLessThanOrEqual(1);

    await region.evaluate(node => node.scrollTo({ top: 400, left: 160 }));
    const after = await measure();
    await expect(header).toBeVisible();
    // The names stuck to the top of the region instead of scrolling away.
    expect(Math.abs(after.namesTop - after.boardTop)).toBeLessThanOrEqual(2);
    // And a lane's name stays at the left edge while the columns pass.
    expect(after.laneNameLeft).toBeGreaterThanOrEqual(after.boardLeft);
    expect(after.laneNameLeft - after.boardLeft).toBeLessThan(80);
    expect(after.bodyOverflow).toBeLessThanOrEqual(1);
  });

  test('files a card in another lane AND another column in one write', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);
    await settleBoard(page);

    const from = await grip(page, 'À trier');
    const to = await centre(page, cell(page, HOME, 'in_progress'));
    await drag(page, from, to);
    await page.mouse.up();

    await expect.poll(() => world.moves.length).toBe(1);
    expect(world.moves[0]).toEqual({ status: 'in_progress', position: 0, category_id: HOME });
    await expect(cell(page, HOME, 'in_progress')).toContainText('À trier');
    await expect(lane(page, 'unfiled')).not.toContainText('À trier');
  });

  test('files a card under an empty lane from its header, and leaves it in its column', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);
    await settleBoard(page);

    const from = await grip(page, 'Repeindre le salon');
    const to = await centre(page, lane(page, WORK).locator('header'));
    await drag(page, from, to);
    await page.mouse.up();

    await expect.poll(() => world.moves.length).toBe(1);
    expect(world.moves[0]).toMatchObject({ status: 'todo', category_id: WORK });
    await expect(cell(page, WORK, 'todo')).toContainText('Repeindre le salon');
  });

  test('un-files a card explicitly when it is dropped in the unfiled lane', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);
    await settleBoard(page);

    const from = await grip(page, 'Poncer la porte');
    const to = await centre(page, cell(page, 'unfiled', 'done'));
    await drag(page, from, to);
    await page.mouse.up();

    await expect.poll(() => world.moves.length).toBe(1);
    // `null` and « unchanged » are one wire value: leaving a category is SAID.
    expect(world.moves[0]).toEqual({ status: 'done', position: 0, clear_category: true });
  });

  test('moves a card to the next lane with the keyboard, and says where it went', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);
    // The board in view, as for the pointer gestures: every lane this case
    // names is on screen before a key is pressed.
    await settleBoard(page);

    // What a screen reader is told, read from the drag's own live region.
    const said = page.locator('[id^="DndLiveRegion"]');
    await card(page, 'À trier').focus();
    await page.keyboard.press('Space');
    await expect(said).toContainText('À faire, couloir À catégoriser');
    await sensorListening(page);
    await page.keyboard.press('ArrowDown');
    // One step down is the next LANE, same column — and it is said.
    await expect(said).toContainText('au-dessus de À faire, couloir Maison');
    await page.keyboard.press('Space');
    await expect(said).toContainText('déposé dans À faire, couloir Maison');

    await expect.poll(() => world.moves.length).toBe(1);
    expect(world.moves[0]).toMatchObject({ status: 'todo', category_id: HOME });
    await expect(lane(page, HOME)).toContainText('À trier');
  });

  test('keeps a ticket held for somebody else in their lane', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);
    await settleBoard(page);
    const opacity = (key: string) =>
      lane(page, key).evaluate(node => getComputedStyle(node).opacity);

    const from = await grip(page, 'Relire le devis');
    const to = await centre(page, cell(page, HOME, 'todo'));
    await drag(page, from, to);

    // In the air: every lane but its owner's is closed, and looks it.
    await expect.poll(() => opacity(HOME)).toBe('0.5');
    expect(await opacity('unfiled')).toBe('0.5');
    expect(await opacity(SITE)).toBe('1');
    await page.mouse.up();

    // Put down: the lanes re-open and nothing was asked of the server.
    await expect.poll(() => opacity(HOME)).toBe('1');
    expect(world.moves).toEqual([]);
    await expect(lane(page, SITE)).toContainText('Relire le devis');

    // Inside its lane it still moves like any card.
    const again = await grip(page, 'Relire le devis');
    const done = await centre(page, cell(page, SITE, 'done'));
    await drag(page, again, done);
    await page.mouse.up();
    await expect.poll(() => world.moves.length).toBe(1);
    expect(world.moves[0]).toEqual({ status: 'done', position: 1 });
  });

  test('remembers a folded lane across a reload', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(standardWorld().routes);
    await open(page);

    const fold = page.getByRole('button', { name: 'Replier Maison' });
    await fold.click();
    await expect(cell(page, HOME, 'todo')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Déplier Maison' })).toBeFocused();
    // Folded, it still counts what it holds.
    await expect(page.getByTestId(`lane-count-${HOME}`)).toHaveText('3 tickets');

    await page.reload();
    await waitForHydration(page, CARD);
    await expect(page.getByRole('button', { name: 'Déplier Maison' })).toBeVisible();
    await expect(cell(page, HOME, 'todo')).toHaveCount(0);
  });

  test('narrows to a lane and stops drawing the ones the filter empties', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(standardWorld().routes);
    const narrowed = page.waitForRequest(request =>
      request.url().includes(`category=${HOME}`)
    );
    await open(page);

    await page.getByRole('combobox', { name: 'Catégorie', exact: true }).click();
    await expect(page.getByRole('option', { name: 'Chantier · Marie' })).toBeVisible();
    await page.getByRole('option', { name: 'Maison', exact: true }).click();

    await narrowed;
    await expect(page).toHaveURL(new RegExp(`category=${HOME}`));
  });

  test('administers the categories: add, reorder under the cursor, delete with its count', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);

    await page.getByRole('button', { name: 'Catégories', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Catégories de tickets' })).toBeVisible();
    // The reader's own, in order — never Marie's, which is not theirs to manage.
    await expect(dialog.getByRole('listitem')).toHaveCount(2);
    await expect(dialog.getByText('2 sur 20')).toBeVisible();
    await expect(dialog.getByRole('textbox', { name: 'Nom de Maison' })).toHaveValue('Maison');

    const { blocking, summary } = await scanPage(page, testInfo, 'workboard-categories', '[role="dialog"]');
    expect(blocking, summary).toHaveLength(0);

    // Add: Enter, the field empties and keeps the cursor.
    const fresh = dialog.getByRole('textbox', { name: 'Nouvelle catégorie' });
    await fresh.fill('Jardin');
    await fresh.press('Enter');
    await expect(dialog.getByRole('listitem')).toHaveCount(3);
    await expect(fresh).toHaveValue('');
    await expect(fresh).toBeFocused();
    expect(world.categoryWrites[0]).toEqual({ method: 'POST', body: { name: 'Jardin' } });
    // The board behind was re-read: the new lane exists.
    await expect(page.getByTestId(/^lane-44444444/)).toHaveCount(1);

    // Reorder with the keyboard: the cursor follows the category that moved,
    // so pressing twice moves it twice.
    const down = dialog.getByRole('button', { name: 'Descendre Maison' });
    await down.focus();
    await page.keyboard.press('Enter');
    await expect
      .poll(() =>
        dialog
          .getByRole('textbox', { name: /^Nom de / })
          .evaluateAll(fields => fields.map(field => (field as HTMLInputElement).value))
      )
      .toEqual(['Travail', 'Maison', 'Jardin']);
    await expect(down).toBeFocused();
    await page.keyboard.press('Enter');
    await expect
      .poll(() =>
        dialog
          .getByRole('textbox', { name: /^Nom de / })
          .evaluateAll(fields => fields.map(field => (field as HTMLInputElement).value))
      )
      .toEqual(['Travail', 'Jardin', 'Maison']);
    await expect(down).toBeFocused();
    expect(world.categoryWrites.slice(1)).toEqual([
      { method: 'PATCH', id: HOME, body: { position: 1 } },
      { method: 'PATCH', id: HOME, body: { position: 2 } },
    ]);

    // Rename on leaving the field.
    const name = dialog.getByRole('textbox', { name: 'Nom de Travail' });
    await name.fill('Bureau');
    await name.press('Tab');
    await expect(dialog.getByRole('textbox', { name: 'Nom de Bureau' })).toHaveValue('Bureau');
    expect(world.categoryWrites.at(-1)).toEqual({
      method: 'PATCH',
      id: WORK,
      body: { name: 'Bureau' },
    });

    // Delete: the question states the EXACT number of tickets sent back.
    await dialog.getByRole('button', { name: 'Supprimer Maison' }).click();
    const question = page.getByRole('alertdialog');
    await expect(question).toContainText('« Maison » contient 3 tickets');
    await expect(question).toContainText('aucun ticket n\'est supprimé');
    await question.getByRole('button', { name: 'Supprimer', exact: true }).click();
    await expect(dialog.getByRole('listitem')).toHaveCount(2);
    expect(world.categoryWrites.at(-1)).toEqual({ method: 'DELETE', id: HOME });
    // The cursor landed somewhere a person can go on from.
    await expect(fresh).toBeFocused();

    await dialog.getByRole('button', { name: 'Fermer', exact: true }).last().click();
    await expect(dialog).toHaveCount(0);
    // Its tickets are back in the unfiled lane — none was deleted.
    await expect(lane(page, 'unfiled')).toContainText('Repeindre le salon');
    await expect(lane(page, 'unfiled')).toContainText('Poncer la porte');
    await expect(page.getByTestId(`lane-${HOME}`)).toHaveCount(0);
  });

  test('has no blocking accessibility violation', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate({ language: 'fr' });
    await mockApi(standardWorld().routes);
    await open(page);

    const { blocking, summary } = await scanPage(page, testInfo, 'workboard-lanes-desktop');
    expect(blocking, summary).toHaveLength(0);
  });
});

test.describe('the workboard in lanes — on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('shows one column grouped by lane, and files a ticket from its card', async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }, testInfo) => {
    test.skip(browserName === 'firefox', 'Firefox has no mobile emulation');
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);

    // ONE column and its picker; the lanes are its groups.
    await expect(page.getByRole('combobox', { name: 'Colonne affichée' })).toBeVisible();
    await expect(lanes(page)).toHaveCount(4);
    await expect(cell(page, HOME, 'todo')).toContainText('Repeindre le salon');
    await expect(cell(page, HOME, 'done')).toHaveCount(0);
    // Each lane counts what is under it: the column on screen.
    await expect(page.getByTestId(`lane-count-${HOME}`)).toHaveText('2 tickets');

    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
    expect(await overflow()).toBeLessThanOrEqual(1);

    // Nothing drags: the category is a list on the OWNER's cards only.
    await expect(page.getByRole('combobox', { name: /^Catégorie de / })).toHaveCount(3);
    await expect(
      page.getByRole('combobox', { name: 'Catégorie de Relire le devis' })
    ).toHaveCount(0);
    await page.getByRole('combobox', { name: 'Catégorie de À trier' }).click();
    await page.getByRole('option', { name: 'Travail', exact: true }).click();
    await expect.poll(() => world.patches.length).toBe(1);
    expect(world.patches[0]).toEqual({ category_id: WORK });
    await expect(cell(page, WORK, 'todo')).toContainText('À trier');

    await expectNoZoomOnFocus(page);
    const { blocking, summary } = await scanPage(page, testInfo, 'workboard-lanes-phone');
    expect(blocking, summary).toHaveLength(0);

    // At 320 px — the narrowest phone — still nothing overflows.
    await page.setViewportSize({ width: 320, height: 640 });
    await expect(cell(page, HOME, 'todo')).toBeVisible();
    expect(await overflow()).toBeLessThanOrEqual(1);
  });

  test('keeps the board’s figures folded until asked, and asks the server nothing before', async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }) => {
    test.skip(browserName === 'firefox', 'Firefox has no mobile emulation');
    const { world, routes } = standardWorld();
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);

    await expect(glance(page)).not.toHaveAttribute('open', '');
    expect(world.summaryReads).toBe(0);
    // Nothing marks a column off another: there is one.
    await expect(page.locator('[data-column-rule]')).toHaveCount(0);

    await glance(page).locator('summary').click();
    await expect(glance(page).getByRole('button', { name: /Sur ton tableau/ })).toContainText('5');
    expect(world.summaryReads).toBeGreaterThan(0);
    // Two figures a row, and the page still does not scroll sideways.
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      )
    ).toBeLessThanOrEqual(0);
    // A figure narrows the board in place on a phone too.
    await glance(page).getByRole('button', { name: /Maison/ }).click();
    await expect.poll(() => world.reads.at(-1) ?? '').toContain(`category=${HOME}`);
  });

  test('pins a lane’s name under the application header while its cards scroll', async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }) => {
    test.skip(browserName === 'firefox', 'Firefox has no mobile emulation');
    const crowd = Array.from({ length: 10 }, (_, index) =>
      ticket(index + 10, { title: `Carte ${index}`, position: index, category_id: HOME })
    );
    const { routes } = boardWorld(crowd, [
      { id: HOME, owner_user_id: ME, name: 'Maison', position: 0 },
    ]);
    await authenticate({ language: 'fr' });
    await mockApi(routes);
    await open(page);

    const fifth = card(page, 'Carte 5');
    await fifth.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, 200));
    const pinned = await page.evaluate(laneId => {
      const header = document.querySelector<HTMLElement>(`[data-testid="lane-${laneId}"] header`)!;
      const bar = document.querySelector<HTMLElement>('header')!;
      const top = header.getBoundingClientRect().top;
      // What a finger would actually hit at the name's place.
      const hit = document.elementFromPoint(40, top + header.offsetHeight / 2);
      return {
        top,
        barBottom: bar.getBoundingClientRect().bottom,
        hitsTheName: header.contains(hit),
      };
    }, HOME);

    // Stuck right under the application header, and on top of its own cards.
    expect(Math.abs(pinned.top - pinned.barBottom)).toBeLessThanOrEqual(2);
    expect(pinned.hitsTheName).toBe(true);
  });
});

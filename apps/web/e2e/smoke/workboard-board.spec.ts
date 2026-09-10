/**
 * The board, in a real browser (ADR-276, lot 4).
 *
 * Three things only a browser proves, and each was a defect before this lot:
 *
 * 1. **`/dashboard/workboard/<id>` resolves.** The backend puts that exact
 *    path in EVERY ticket notification (`notifications.py::ticket_url`), and
 *    it answered 404 until this lot — measured 2026-09-09. A unit test cannot
 *    see a missing App Router route.
 * 2. **At 390 px the body never scrolls sideways.** Seven columns in a row is
 *    the classic way a kanban breaks a phone; the board switches to ONE column
 *    and a picker instead, and only a laid-out page can be measured.
 * 3. **Changing a ticket's column writes what the server expects.** The spec
 *    counts what is ASKED of the server, which is the only oracle that
 *    survives a refactor of the gesture — and it survived one: the card's
 *    `<select>` is gone, the panel carries the control, the request is the
 *    same.
 *
 * A fourth thing this file proves by existing: it had never been RUN. It
 * waited for a `<form>` the board does not contain, so all three cases timed
 * out — in CI too, where the managed build would have redded the job. A
 * hydration probe names a node the page ACTUALLY renders.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const TICKET_ID = '8f0e1d2c-1111-4000-8000-000000000001';

/** A node the board really renders — the board has no `<form>` to wait on. */
const CARD = '[data-testid="ticket-card"]';

/** The id the auth fixture signs in with: the board's owner IS that account. */
const E2E_USER_ID = '00000000-0000-4000-8000-000000000001';

function ticket(overrides: Record<string, unknown> = {}) {
  return {
    id: TICKET_ID,
    owner_user_id: E2E_USER_ID,
    parent_id: null,
    title: 'Réserver la salle',
    description: 'Douze personnes, le 20.',
    status: 'todo',
    priority: 'high',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: E2E_USER_ID,
    position: 0,
    follow_owner: false,
    follow_assignee: false,
    created_by: 'user',
    status_changed_at: '2026-09-09T10:00:00Z',
    run_count: 0,
    run_claimed_at: null,
    last_run_at: null,
    last_run_outcome: null,
    last_run_error: null,
    last_run_tokens_in: null,
    last_run_tokens_out: null,
    last_run_cost_eur: null,
    created_at: '2026-09-09T10:00:00Z',
    updated_at: '2026-09-09T10:00:00Z',
    ...overrides,
  };
}

const COUNTS = {
  idea: 0,
  todo: 1,
  in_progress: 0,
  waiting: 0,
  validating: 0,
  done: 0,
};

function boardRoutes(
  moves: unknown[],
  row: Record<string, unknown> = ticket(),
  counts: Record<string, number> = COUNTS
): MockRoute[] {
  return [
    {
      url: '**/api/v1/workboard/tickets?**',
      method: 'GET',
      json: { tickets: [row], total: 1, counts_by_status: counts },
    },
    {
      url: '**/api/v1/workboard/tickets',
      method: 'GET',
      json: { tickets: [row], total: 1, counts_by_status: counts },
    },
    {
      url: `**/api/v1/workboard/tickets/${TICKET_ID}`,
      method: 'GET',
      json: { ticket: row, children: [], comments: [], events: [] },
    },
    {
      url: `**/api/v1/workboard/tickets/${TICKET_ID}`,
      method: 'PATCH',
      handler: async route => {
        moves.push(route.request().postDataJSON());
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ticket({ status: 'done' })),
        });
      },
    },
    { url: '**/api/v1/peers/connections', json: [] },
    { url: '**/api/v1/notifications/hub-counts', json: { workboard: 0 } },
  ];
}

test.describe('the workboard', () => {
  test('opens on the desktop board and changes a column from the panel', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const moves: unknown[] = [];
    await mockApi(boardRoutes(moves));

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);

    // The seven columns, and the card in the one it belongs to.
    await expect(page.getByRole('region', { name: 'À faire' })).toBeVisible();
    await expect(page.getByTestId('ticket-card')).toBeVisible();

    // The card carries NO column control: it sits in the column that names it.
    await expect(page.getByTestId('ticket-card').getByRole('combobox')).toHaveCount(0);

    await page.getByRole('button', { name: 'Réserver la salle', exact: true }).click();
    await page.getByRole('dialog').getByRole('combobox', { name: 'Colonne', exact: true }).click();
    await page.getByRole('option', { name: 'Terminé', exact: true }).click();

    await expect.poll(() => moves.length).toBe(1);
    expect(moves[0]).toMatchObject({ status: 'done' });
  });

  test('draws « À confirmer » only while a confirmation waits, and says how to answer', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Lot 7: the eighth column exists for the tickets LIA handed back with an
    // action to confirm — and for nothing else, so a board with none never
    // pays for it. The panel then names the protocol: comment, then hand over.
    await authenticate({ language: 'fr' });
    const confirming = ticket({ status: 'confirming', last_run_outcome: 'confirming' });
    await mockApi(boardRoutes([], confirming, { ...COUNTS, todo: 0, confirming: 1 }));

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);

    await expect(page.getByRole('region', { name: 'À confirmer' })).toBeVisible();
    await expect(
      page.getByRole('region', { name: 'À confirmer' }).getByTestId('ticket-card')
    ).toBeVisible();

    await page.getByRole('button', { name: 'Réserver la salle', exact: true }).click();
    await expect(page.getByRole('dialog').getByRole('note')).toContainText('attend votre accord');
  });

  test('never draws « À confirmer » on a board with nothing to confirm', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardRoutes([]));

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);

    await expect(page.getByRole('region', { name: 'À faire' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'À confirmer' })).toHaveCount(0);
  });

  test('hands the ticket to LIA from the panel', async ({ page, authenticate, mockApi }) => {
    // « Who holds it » is a control, not a read-only badge: the owner may hand
    // the ticket to LIA, to a connected peer, or take it back.
    await authenticate({ language: 'fr' });
    const writes: unknown[] = [];
    await mockApi(boardRoutes(writes));

    await page.goto(`/fr/dashboard/workboard/${TICKET_ID}`);
    await waitForHydration(page, CARD);

    await page
      .getByRole('dialog')
      .getByRole('combobox', { name: 'Détenu par', exact: true })
      .click();
    await page.getByRole('option', { name: 'LIA', exact: true }).click();

    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ assignee: 'lia' });
  });

  test('a notification link opens the ticket directly', async ({ page, authenticate, mockApi }) => {
    // The path form the backend puts in every ticket notification. It answered
    // 404 before this lot.
    await authenticate({ language: 'fr' });
    await mockApi(boardRoutes([]));

    await page.goto(`/fr/dashboard/workboard/${TICKET_ID}`);
    await waitForHydration(page, CARD);

    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('dialog').getByText('Douze personnes, le 20.')).toBeVisible();
  });

  test('a card never lays its badges under its actions', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // A column is ~208 px wide whatever the screen, so the card's row is the
    // one place a layout runs out of room. Measured, not eyeballed: the first
    // version put three inline icon buttons on the title's line and the text
    // ran under them.
    await authenticate({ language: 'fr' });
    await mockApi(boardRoutes([]));

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);

    const overlap = await page.evaluate(sel => {
      const worst: number[] = [];
      for (const card of document.querySelectorAll(sel)) {
        const actions = card.querySelector('button[aria-haspopup]');
        // Only the row the actions sit ON can collide with them: the title
        // above takes the whole card by design, now that the actions moved
        // down beside the badges.
        const row = actions?.parentElement?.parentElement;
        if (!actions || !row) continue;
        const edge = actions.getBoundingClientRect().left;
        for (const node of row.querySelectorAll('span, div')) {
          const el = node as HTMLElement;
          if (!el.innerText?.trim() || el.contains(actions)) continue;
          const box = el.getBoundingClientRect();
          if (box.width === 0 || box.height === 0) continue;
          worst.push(box.right - edge);
        }
      }
      return Math.max(0, ...worst);
    }, CARD);

    // A couple of pixels of rounding is not an overlap; a word under a button is.
    expect(overlap).toBeLessThanOrEqual(2);
  });

  test('a narrowed link narrows the board on arrival', async ({ page, authenticate, mockApi }) => {
    // The settings page points at « what is late » and « what LIA holds »: the
    // filters START from the URL, and the first read carries them.
    await authenticate({ language: 'fr' });
    await mockApi(boardRoutes([]));
    const narrowed = page.waitForRequest(
      request =>
        request.url().includes('/workboard/tickets?') &&
        request.url().includes('overdue=true') &&
        request.url().includes('assignee=lia')
    );

    await page.goto('/fr/dashboard/workboard?overdue=1&assignee=lia');

    await narrowed;
    await waitForHydration(page, CARD);
    await expect(page.getByRole('checkbox', { name: 'En retard seulement' })).toBeChecked();
    await expect(page.getByRole('combobox', { name: 'Détenu par', exact: true })).toHaveText(/LIA/);
  });

  test('at 390 px the body never scrolls sideways', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    // A LATE ticket: its date passed nine days ago, so the card also states
    // « En retard » under it.
    await mockApi(boardRoutes([], ticket({ due_at: '2026-09-01T10:00:00Z' })));
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);

    // ONE column and its picker, never seven side by side.
    await expect(page.getByRole('combobox', { name: 'Colonne affichée' })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // The two lists on the card: the column, and the holder UNDER it — the
    // same left edge, lower on the screen (owner, 2026-09-10). Geometry only
    // a real layout can answer.
    const column = await page
      .getByRole('combobox', { name: 'Colonne de Réserver la salle' })
      .boundingBox();
    const holder = await page
      .getByRole('combobox', { name: 'Porteur de Réserver la salle' })
      .boundingBox();
    expect(column).not.toBeNull();
    expect(holder).not.toBeNull();
    expect(holder!.y).toBeGreaterThanOrEqual(column!.y + column!.height);
    expect(Math.abs(holder!.x - column!.x)).toBeLessThan(1);

    // « En retard » under the date, its word starting exactly where the
    // date's does: the icon is boxed like the bell above it (owner,
    // 2026-09-10). Again a measurement only a real layout can make.
    const lateCard = page.getByTestId('ticket-card');
    const due = await lateCard.getByText(/^Échéance/).boundingBox();
    const overdue = await lateCard.getByText('En retard', { exact: true }).boundingBox();
    expect(due).not.toBeNull();
    expect(overdue).not.toBeNull();
    expect(overdue!.y).toBeGreaterThan(due!.y);
    expect(Math.abs(overdue!.x - due!.x)).toBeLessThan(1);

    // Nothing drags on a phone: a finger on the card — its bottom line, not
    // the title — opens the ticket (owner, 2026-09-10). A real hit test:
    // the stretched door is a pseudo-element jsdom cannot draw.
    // Bottom RIGHT of the card: the dev server parks its issue badge over the
    // bottom-left corner of the viewport, which is where the first attempt
    // clicked and found the badge instead of the card.
    const card = page.getByTestId('ticket-card');
    await card.scrollIntoViewIfNeeded();
    const box = await card.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x + box!.width - 24, box!.y + box!.height - 10);
    await expect(page.getByRole('dialog')).toBeVisible();
  });

  test('a due date the person picks is the day they read back, and not yet late', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The defect this pins, measured in two timezones: the panel sent
    // `new Date('2026-09-15').toISOString()` — MIDNIGHT UTC — so the ticket
    // was « En retard » at midday on its own due date, and a reader west of
    // Greenwich read back the day BEFORE the one they picked. Only a real
    // browser resolves a local day, which is why it is pinned here.
    await authenticate({ language: 'fr' });
    const patches: Record<string, unknown>[] = [];
    const routes = boardRoutes(patches);
    await mockApi(routes);

    await page.goto(`/fr/dashboard/workboard?ticket=${TICKET_ID}`);
    await expect(page.getByRole('dialog')).toBeVisible();

    const due = page.getByLabel('Échéance');
    await due.fill('2026-12-24');
    await expect.poll(() => patches.length).toBeGreaterThan(0);

    const stored = String(patches.at(-1)?.due_at ?? '');
    expect(stored).not.toBe('');
    const readBack = await page.evaluate(instant => {
      const date = new Date(instant);
      return {
        day: new Intl.DateTimeFormat('en-CA', { dateStyle: 'short' }).format(date),
        lateAtMidday: date.getTime() < new Date('2026-12-24T12:00:00').getTime(),
      };
    }, stored);

    expect(readBack.day).toBe('2026-12-24');
    expect(readBack.lateAtMidday).toBe(false);
  });

  test('folds the filters on a phone and says what they hold', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Owner, 2026-09-10: five controls above ONE column of cards is a wall,
    // and the reader came for their tickets. Folded, the block still has to
    // say what it narrows — otherwise it is opened to find out, which is the
    // scanning the fold exists to spare.
    await authenticate({ language: 'fr' });
    await mockApi(boardRoutes([]));
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/fr/dashboard/workboard?assignee=me&overdue=1');
    await waitForHydration(page, CARD);

    // Closed, and its content really absent from the DOM (a `<details>` that
    // merely HIDES its children would still run their hooks and fetch).
    const summary = page.getByText('Filtres', { exact: true });
    await expect(summary).toBeVisible();
    await expect(page.getByLabel('Chercher un titre')).toHaveCount(0);

    // The exact number of narrowings, and their own words.
    await expect(page.getByText('2', { exact: true })).toBeVisible();
    await expect(page.getByText(/Moi.*En retard/)).toBeVisible();

    await summary.click();
    await expect(page.getByLabel('Chercher un titre')).toBeVisible();

    // Nothing overflows once the block is open either.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('moves a ticket from the list on its card, on a phone', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const moves: unknown[] = [];
    await mockApi(boardRoutes(moves));
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);

    await page.getByRole('combobox', { name: 'Colonne de Réserver la salle' }).click();
    // Each item wears its column's glyph before its name (owner, 2026-09-10)
    // — a native `<option>` could not have. « Terminé » is not the chosen
    // item, so the one SVG it holds is the glyph, never the check mark.
    const done = page.getByRole('option', { name: 'Terminé', exact: true });
    await expect(done.locator('svg')).toHaveCount(1);
    await done.click();

    // The same request the panel writes.
    await expect.poll(() => moves.length).toBe(1);
    expect(moves[0]).toMatchObject({ status: 'done' });
  });

  test('a late ticket wears an inner red frame that breathes only where motion is welcome', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardRoutes([], ticket({ due_at: '2026-09-01T10:00:00Z' })));

    await page.goto('/fr/dashboard/workboard');
    await waitForHydration(page, CARD);
    const card = page.getByTestId('ticket-card');
    const state = () =>
      card.evaluate(element => {
        // The frame is a pseudo-element on the padding box: read it there.
        const frame = getComputedStyle(element, '::before');
        const own = getComputedStyle(element);
        return {
          width: frame.borderTopWidth,
          style: frame.borderTopStyle,
          position: frame.position,
          frameColor: frame.borderTopColor,
          ownColor: own.borderTopColor,
          edgeWidth: own.borderLeftWidth,
          edgeColor: own.borderLeftColor,
          animations: element.getAnimations({ subtree: true }).map(animation => ({
            name: (animation as CSSAnimation).animationName,
            on: (animation.effect as KeyframeEffect | null)?.pseudoElement ?? null,
            duration: Number(animation.effect?.getTiming().duration ?? 0),
          })),
        };
      });

    // The suite runs under `prefers-reduced-motion: reduce`: the frame is
    // there, 2 px, still and red — the animation's end state, never its
    // absence — INSIDE the borders, so the 4 px priority edge keeps its own
    // tone outside it (owner, 2026-09-10).
    const still = await state();
    expect(still).toMatchObject({
      width: '2px',
      style: 'solid',
      position: 'absolute',
      animations: [],
    });
    expect(still.frameColor).not.toBe(still.ownColor);
    expect(still.edgeWidth).toBe('4px');
    expect(still.edgeColor).not.toBe(still.frameColor);

    // Where motion is welcome it breathes — on the pseudo-element — eased,
    // slow, never a blink.
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect
      .poll(async () => (await state()).animations.map(animation => animation.name))
      .toContain('overdue-pulse');
    const pulse = (await state()).animations.find(animation => animation.name === 'overdue-pulse');
    expect(pulse?.on).toBe('::before');
    expect(pulse?.duration).toBeGreaterThanOrEqual(2000);
  });
});

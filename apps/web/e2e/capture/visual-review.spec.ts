/**
 * Visual review captures — a human-eye pass on the surfaces this cycle touched.
 *
 * NOT an assertion suite: `capture/**` is excluded from the default run
 * (`testIgnore` in the Playwright config), and exists so a reviewer can look
 * at what shipped instead of inferring it from the DOM. Run it explicitly
 * against a standalone build when a change is visual.
 */
import { test } from '../fixtures';

import { dashboardShellMocks } from '../fixtures/dashboard-shell';

const OUT = 'test-results/visual-review';

test.describe('visual review', () => {
  const OWNER = '00000000-0000-4000-8000-000000000001';
  const BOARD_ROWS = [
    {
      id: '11111111-1111-4000-8000-000000000001',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Réserver la salle du 20',
      description: null,
      status: 'todo',
      priority: 'urgent',
      start_at: null,
      due_at: '2026-09-01T10:00:00Z',
      assignee_kind: 'human',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
      position: 0,
      follow_owner: true,
      follow_assignee: false,
      created_by: 'user',
      status_changed_at: '2026-09-09T10:00:00Z',
      run_count: 3,
      run_claimed_at: null,
      last_run_at: '2026-09-09T08:30:00Z',
      last_run_outcome: 'success',
      last_run_error: null,
      last_run_tokens_in: 1840,
      last_run_tokens_out: 260,
      last_run_cost_eur: 0.012,
      execution_mode: 'react',
      total_tokens_in: 5420,
      total_tokens_out: 780,
      total_tokens_cache: 2048,
      total_google_requests: 4,
      total_cost_eur: 0.037,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000002',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Relancer le devis',
      description: null,
      status: 'todo',
      priority: 'high',
      start_at: null,
      due_at: '2026-09-30T10:00:00Z',
      assignee_kind: 'human',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000003',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Trier les photos',
      description: null,
      status: 'todo',
      priority: 'medium',
      start_at: null,
      due_at: null,
      assignee_kind: 'human',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000004',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Lire le rapport annuel',
      description: null,
      status: 'todo',
      priority: 'low',
      start_at: null,
      due_at: null,
      assignee_kind: 'human',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000005',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Préparer la réunion',
      description: null,
      status: 'in_progress',
      priority: 'high',
      start_at: null,
      due_at: null,
      assignee_kind: 'lia',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000006',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Choisir le créneau',
      description: null,
      status: 'waiting',
      priority: 'medium',
      start_at: null,
      due_at: null,
      assignee_kind: 'lia',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000007',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Valider la synthèse',
      description: null,
      status: 'validating',
      priority: 'medium',
      start_at: null,
      due_at: null,
      assignee_kind: 'lia',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
    {
      id: '11111111-1111-4000-8000-000000000008',
      owner_user_id: OWNER,
      parent_id: null,
      title: 'Noter l’idée du podcast',
      description: null,
      status: 'idea',
      priority: 'low',
      start_at: null,
      due_at: null,
      assignee_kind: 'human',
      assignee_user_id: null,
      effective_assignee_id: OWNER,
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
      execution_mode: 'react',
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    },
  ];
  const BOARD_COUNTS = {
    idea: 1,
    todo: 4,
    in_progress: 1,
    waiting: 1,
    validating: 1,
    done: 0,
  };
  const boardMocks = [
    ...dashboardShellMocks,
    {
      url: '**/api/v1/workboard/tickets?**',
      json: { tickets: BOARD_ROWS, total: BOARD_ROWS.length, counts_by_status: BOARD_COUNTS },
    },
    {
      url: '**/api/v1/workboard/tickets',
      json: { tickets: BOARD_ROWS, total: BOARD_ROWS.length, counts_by_status: BOARD_COUNTS },
    },
    {
      url: `**/api/v1/workboard/tickets/${BOARD_ROWS[0].id}`,
      json: {
        ticket: BOARD_ROWS[0],
        children: [],
        comments: [
          {
            id: 'c1',
            author_kind: 'user',
            author_user_id: OWNER,
            body: 'Douze personnes, plutôt le matin.',
            run_id: null,
            created_at: '2026-09-08T09:12:00Z',
          },
          {
            id: 'c2',
            author_kind: 'lia',
            author_user_id: null,
            body: "J'ai trouvé deux créneaux libres.\n\nMardi 10h ou jeudi 14h ?",
            run_id: 'r1',
            created_at: '2026-09-08T09:40:00Z',
          },
        ],
        events: [
          {
            id: 'e1',
            actor_kind: 'user',
            actor_user_id: OWNER,
            kind: 'created',
            payload: { status: 'todo' },
            created_at: '2026-09-08T09:00:00Z',
          },
          {
            id: 'e2',
            actor_kind: 'user',
            actor_user_id: OWNER,
            kind: 'priority_changed',
            payload: { from: 'medium', to: 'urgent' },
            created_at: '2026-09-08T09:05:00Z',
          },
          {
            id: 'e3',
            actor_kind: 'user',
            actor_user_id: OWNER,
            kind: 'dates_changed',
            payload: {
              from_start: null,
              to_start: null,
              from_due: null,
              to_due: '2026-09-01T10:00:00Z',
            },
            created_at: '2026-09-08T09:06:00Z',
          },
          {
            id: 'e4',
            actor_kind: 'lia',
            actor_user_id: null,
            kind: 'assigned',
            payload: { to_kind: 'human', reason: 'handed_back' },
            created_at: '2026-09-08T09:40:00Z',
          },
        ],
      },
    },
    { url: '**/api/v1/peers/connections', json: [] },
  ];

  test('workboard — seven columns, the priority ramp and the late mark', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/workboard');
    await page.getByTestId('ticket-card').first().waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/workboard-board.png`, fullPage: false });
  });

  test('workboard — the panel, where a ticket is edited and handed over', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/fr/dashboard/workboard/${BOARD_ROWS[0].id}`);
    await page.getByRole('dialog').waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.getByRole('dialog').screenshot({ path: `${OUT}/workboard-panel.png` });
  });

  test('workboard — the panel, scrolled to the comments and the history', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/fr/dashboard/workboard/${BOARD_ROWS[0].id}`);
    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ timeout: 60_000 });
    await dialog.getByRole('region', { name: 'Historique' }).scrollIntoViewIfNeeded();
    await page.waitForTimeout(1200);
    await dialog.screenshot({ path: `${OUT}/workboard-panel-comments.png` });
  });

  test('workboard on a tablet — still one column, below the lg switch', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/fr/dashboard/workboard');
    await page.getByTestId('ticket-card').first().waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/workboard-tablet.png`, fullPage: false });
  });

  test('workboard on a phone — one column, and a card a finger can grab', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/workboard');
    await page.getByTestId('ticket-card').first().waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/workboard-phone.png`, fullPage: false });
  });

  test('workboard on a phone — one card, with its two lists', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/workboard');
    const card = page.getByTestId('ticket-card').first();
    await card.waitFor({ timeout: 60_000 });
    // At the TOP of the viewport: parked at its bottom, the card sits under the
    // companion avatar and the dev server's issue badge.
    await card.evaluate(element => element.scrollIntoView({ block: 'start' }));
    await page.waitForTimeout(1200);
    await card.screenshot({ path: `${OUT}/workboard-phone-card.png` });
  });

  test('workboard on a phone — the column list open, a glyph before every name', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(boardMocks);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/workboard');
    const card = page.getByTestId('ticket-card').first();
    await card.waitFor({ timeout: 60_000 });
    await card.evaluate(element => element.scrollIntoView({ block: 'start' }));
    await page.waitForTimeout(600);
    await card.getByRole('combobox', { name: /^Colonne de/ }).click();
    await page.getByRole('listbox').waitFor();
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/workboard-phone-list.png`, fullPage: false });
  });

  // ADR-277: the picker of the pinned sections, and the dock it feeds, on the
  // same screen — three sections pinned, the section open.
  const shortcutsMocks = [
    ...dashboardShellMocks,
    {
      url: '**/api/v1/users/me/settings-shortcuts',
      json: { shortcuts: ['theme', 'font', 'notifications'], max_count: 5 },
    },
  ];

  test('settings — my shortcuts, and the dock they feed', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr', settings_shortcuts: ['theme', 'font', 'notifications'] });
    await mockApi(shortcutsMocks);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/settings?section=my-shortcuts');
    await page.getByRole('checkbox', { name: 'Police' }).waitFor({ timeout: 60_000 });
    await page.getByRole('navigation', { name: /raccourcis/i }).hover();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/shortcuts-section.png`, fullPage: false });
  });

  test('the shortcuts dock on a phone', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr', settings_shortcuts: ['theme', 'font', 'notifications'] });
    await mockApi(shortcutsMocks);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/settings');
    await page.getByRole('navigation', { name: /raccourcis/i }).waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/shortcuts-phone.png`, fullPage: false });
  });

  test('settings — the workboard at a glance', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([
      ...dashboardShellMocks,
      {
        url: '**/api/v1/workboard/summary',
        json: {
          total: 8,
          counts_by_status: {
            idea: 1,
            todo: 4,
            in_progress: 1,
            waiting: 1,
            confirming: 0,
            validating: 1,
            done: 0,
          },
          overdue: 1,
          held_by_lia: 3,
          needs_me: 2,
          owned: 7,
          max_tickets: 200,
          max_runs_per_ticket: 10,
          runs_total: 5,
          tokens_in: 9420,
          tokens_out: 1310,
          tokens_cache: 2048,
          google_requests: 6,
          cost_eur: 0.07,
        },
      },
    ]);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/settings?section=workboard');
    await page.getByRole('progressbar').waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/settings-workboard.png`, fullPage: false });
  });

  test('settings hub', async ({ page, authenticate, mockApi }) => {
    // The dashboard's theme is a stored user preference, not
    // `prefers-color-scheme`, so emulating the media query here would
    // capture the same picture twice. Both themes are covered where they
    // are actually switchable: the public axe scans.
    await authenticate({ language: 'fr' });
    await mockApi([
      ...dashboardShellMocks,
      { url: '**/api/v1/connectors', json: { connectors: [] } },
    ]);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/settings');
    await page.getByRole('navigation', { name: 'Sections des réglages' }).waitFor({
      timeout: 60_000,
    });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/settings-hub.png`, fullPage: false });
  });
  test('settings rail on a phone', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(dashboardShellMocks);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/settings');
    await page.getByRole('navigation', { name: 'Sections des réglages' }).waitFor({
      timeout: 60_000,
    });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${OUT}/settings-rail-phone.png`, fullPage: false });
  });

  test('landing release band', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr#changelog');
    await page.waitForTimeout(2500);
    await page.locator('#changelog').scrollIntoViewIfNeeded();
    await page.waitForTimeout(1200);
    await page.locator('#changelog').screenshot({ path: `${OUT}/landing-changelog.png` });
  });

  test('more page — the new settings-shell card', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    await page.goto('/fr/more#more-find');
    await page.waitForTimeout(2500);
    await page.locator('#more-find').scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    await page.locator('#more-find').screenshot({ path: `${OUT}/more-find-section.png` });
  });

  test('capability constellation', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([
      ...dashboardShellMocks,
      {
        url: '**/api/v1/capabilities',
        json: {
          nodes: [
            { key: 'connectors', active: true, detail: 4 },
            { key: 'memory', active: true, detail: 128 },
            { key: 'personality', active: true, detail: null },
            { key: 'voice', active: false, detail: null },
            { key: 'proactivity', active: true, detail: null },
            { key: 'images', active: true, detail: null },
            { key: 'documents', active: true, detail: null },
            { key: 'interests', active: true, detail: 7 },
            { key: 'routines', active: false, detail: 0 },
            { key: 'relations', active: true, detail: 3 },
            { key: 'habits', active: false, detail: 0 },
            { key: 'peers', active: true, detail: 2 },
            { key: 'channels', active: false, detail: 0 },
            { key: 'telephony', active: false, detail: 0 },
            { key: 'spaces', active: true, detail: 5 },
            { key: 'journals', active: true, detail: 42 },
            { key: 'skills', active: true, detail: 6 },
            { key: 'plugins', active: false, detail: 0 },
            { key: 'mcp_servers', active: true, detail: 2 },
          ],
          live: 12,
          total: 19,
        },
      },
    ]);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto('/fr/dashboard/capabilities');
    await page.waitForTimeout(4000);
    await page.screenshot({ path: `${OUT}/capability-constellation.png`, fullPage: false });
  });
});

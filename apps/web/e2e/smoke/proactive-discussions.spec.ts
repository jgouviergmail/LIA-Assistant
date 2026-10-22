/** Personal controls are reachable on real settings, with fictional API data only. */
import type { Locator } from '@playwright/test';
import { test, expect, idleNotificationStream } from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

/**
 * Open the two context panels (owner request 2026-10-21): « Contexte », where
 * the work stands (rebuild, activity, last run), then « Données du contexte »,
 * the elements it holds (filters, switches, purge).
 */
async function openContextPanels(section: Locator): Promise<void> {
  for (const title of [/^Contexte$/, /^Données du contexte$/]) {
    await section.locator('summary').filter({ hasText: title }).click();
  }
}

const itemId = 'd862582d-e529-4803-a5a4-b11f98c17572';
const sources = [
  'calendar',
  'emails',
  'contacts',
  'tasks',
  'weather',
  'location',
  'memories',
  'journals',
  'portrait',
  'open_loops',
  'habits',
  'relations',
  'health',
  'conversations',
  'meetings',
  'peers',
  'peer_messages',
  'interests',
  'reminders',
  'scheduled_actions',
  'workboard',
  'sms',
];

// The panel is read in both themes: its figures and badges must hold in the dark too.
const samples = [
  { width: 320, theme: 'light' },
  { width: 390, theme: 'light' },
  { width: 1280, theme: 'light' },
  { width: 1280, theme: 'dark' },
] as const;

for (const { width, theme } of samples) {
  test(`discussions controls and context lifecycle @ ${width}px ${theme}`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.setViewportSize({ width, height: 950 });
    await prepareTheme(page, theme);
    await authenticate({ language: 'fr', theme });
    let policy = {
      enabled: false,
      start_hour: 9,
      end_hour: 20,
      timezone: 'Europe/Paris',
      daily_max: 2,
      sources: ['calendar'],
      sensitive_topics: [],
      forbidden_topics: [],
      paused_until: null,
      revision: 0,
    };
    const writes: unknown[] = [];
    let excluded = false;
    let purged = false;
    let epoch = 0;
    let budgetConfigured = true;
    let refreshRequested = false;
    const proof = {
      root: 'fictional-root',
      reference: 'calendar:fiction',
      source: 'calendar',
      source_account: 'fictional-account',
      object_id: 'fiction',
      version: '1',
      observed_at: '2026-10-20T12:00:00Z',
      occurred_at: null,
      expires_at: '2027-01-20T12:00:00Z',
      assertion: 'planned',
      required_sources: [],
      sensitive_topics: [],
      support_roots: [],
    };
    function context() {
      return {
        generation: 1,
        context_epoch: epoch,
        forgotten_at: null,
        refresh_requested: refreshRequested,
        items: purged
          ? []
          : [
              {
                id: itemId,
                kind: 'observation',
                summary: 'Un rendez-vous prévu pour préparer une randonnée.',
                qualification: 'planned',
                revision: 1,
                generation: 1,
                proofs: [proof],
                excluded,
                explicitly_excluded: excluded,
              },
            ],
        exclusions: excluded ? [{ item_id: itemId, roots: [proof.root] }] : [],
        total: purged ? 0 : 1,
        next_cursor: null,
        exclusions_total: excluded ? 1 : 0,
        exclusions_next_cursor: null,
        coverage: [],
      };
    }
    // The last automatic run, its counts and its own cost: fictional figures.
    const lastRun = {
      kind: 'opening',
      state: 'skipped',
      claimed_at: '2026-10-21T15:32:00Z',
      settled_at: '2026-10-21T15:33:00Z',
      reason: 'decision_skip',
      stats: {
        pages: { ok: 2 },
        facts_read: 4,
        facts_admitted: 4,
        facts_offered: 2,
        facts_unclassified: 0,
        context_calls: 1,
        proposals: 1,
        proposals_refused: 0,
        research_refused: 0,
        context_updates: 1,
        items: 1,
      },
      usage: {
        tokens_in: 1200,
        tokens_out: 300,
        tokens_cache: 0,
        google_requests: 0,
        cost_eur: 0.0042,
      },
    };
    // An earlier rebuild the person asked for, settled before that run.
    const lastRebuild = {
      ...lastRun,
      kind: 'rebuild',
      state: 'completed',
      claimed_at: '2026-10-21T14:46:00Z',
      settled_at: '2026-10-21T14:47:00Z',
      reason: 'context_ready',
    };
    const contextQueries: string[] = [];
    function settings() {
      return {
        policy,
        sources: sources.map(key => ({
          key,
          operations: ['recent'],
          indivisible: key === 'portrait',
          dependencies: key === 'weather' ? ['location'] : [],
        })),
        producer_enabled: true,
        budget_configured: budgetConfigured,
        pause_hours: 24,
      };
    }
    await mockApi([
      idleNotificationStream,
      {
        url: '**/api/v1/system-settings/debug-panel-status',
        json: { enabled: false, user_access_available: false },
      },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      {
        url: '**/api/v1/proactive-discussions/settings',
        handler: async route => {
          if (route.request().method() === 'PATCH') {
            const body = route.request().postDataJSON();
            writes.push(body);
            expect(body.expected_revision).toBe(policy.revision);
            policy = { ...policy, ...body.changes, revision: policy.revision + 1 };
          }
          await route.fulfill({ json: settings() });
        },
      },
      {
        url: '**/api/v1/proactive-discussions/context?**',
        handler: route => {
          contextQueries.push(new URL(route.request().url()).searchParams.get('query') ?? '');
          return route.fulfill({ json: context() });
        },
      },
      {
        url: '**/api/v1/proactive-discussions/activity',
        handler: route =>
          route.fulfill({
            json: {
              rebuild: refreshRequested ? 'requested' : 'idle',
              obstacle: null,
              last_rebuild: lastRebuild,
              last_update: lastRun,
              last_run: lastRun,
              budget: {
                configured: budgetConfigured,
                reached: budgetConfigured ? 'owner_day' : null,
                resets_at: budgetConfigured ? '2026-10-22T00:00:00Z' : null,
              },
            },
          }),
      },
      {
        url: `**/api/v1/proactive-discussions/context/${itemId}/usability`,
        method: 'PATCH',
        handler: async route => {
          const body = route.request().postDataJSON();
          expect(body.expected_epoch).toBe(epoch);
          excluded = !body.usable;
          epoch++;
          await route.fulfill({ json: context() });
        },
      },
      {
        url: '**/api/v1/proactive-discussions/context/purge-preview',
        method: 'POST',
        handler: route =>
          route.fulfill({
            json: { context_epoch: epoch, generation: 1, selected_count: 1, affected_count: 1 },
          }),
      },
      {
        url: '**/api/v1/proactive-discussions/context/purge',
        method: 'POST',
        handler: async route => {
          const body = route.request().postDataJSON();
          expect(body.expected_epoch).toBe(epoch);
          expect(body.expected_generation).toBe(1);
          writes.push(body);
          purged = true;
          epoch++;
          await route.fulfill({ json: context() });
        },
      },
      {
        url: '**/api/v1/proactive-discussions/context/rebuild',
        method: 'POST',
        handler: async route => {
          const body = route.request().postDataJSON();
          expect(body.expected_epoch).toBe(epoch);
          writes.push(body);
          refreshRequested = true;
          epoch++;
          await route.fulfill({ json: context() });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=proactive-discussions');
    const section = page.locator('#settings-section-proactive-discussions');
    const enabled = section.getByRole('switch', {
      name: 'Autoriser LIA à engager une discussion',
      exact: true,
    });
    await expect(enabled).not.toBeChecked({ timeout: 45000 });
    await enabled.focus();
    await page.keyboard.press('Space');
    await expect(enabled).toBeChecked();
    await expect(enabled).toBeFocused();
    await openContextPanels(section);
    await expect(
      section.getByText('Un rendez-vous prévu pour préparer une randonnée.')
    ).toBeVisible();
    // The rebuild first: left of the latest update when the card holds both on
    // one line, above it otherwise.
    const rebuiltAt = await section
      .getByText('Dernière reconstruction', { exact: true })
      .boundingBox();
    const updatedAt = await section
      .getByText('Dernière mise à jour du contexte', { exact: true })
      .boundingBox();
    expect(rebuiltAt && updatedAt).toBeTruthy();
    if (width >= 1280) {
      expect(rebuiltAt!.x).toBeLessThan(updatedAt!.x);
      expect(Math.abs(rebuiltAt!.y - updatedAt!.y)).toBeLessThan(2);
    } else {
      expect(rebuiltAt!.y).toBeLessThan(updatedAt!.y);
    }
    // The last run's own outcome, and — only because one stops LIA — the ceiling reached.
    const lastRunSection = section.getByRole('region', { name: 'Dernier passage', exact: true });
    await expect(lastRunSection.getByText('Automatique', { exact: true })).toBeVisible();
    await expect(lastRunSection.getByText('Rien ne justifiait une discussion.')).toBeVisible();
    await expect(
      section.getByText(/^Ton plafond de dépense du jour est atteint : aucune discussion/)
    ).toBeVisible();
    await expect(section.getByRole('heading', { name: 'Plafonds de dépense' })).toHaveCount(0);
    // The search applies itself once typing pauses: no « Filtrer » button any more.
    await expect(section.getByRole('button', { name: 'Filtrer', exact: true })).toHaveCount(0);
    await section.getByRole('searchbox', { name: 'Rechercher dans les résumés' }).fill('randonnée');
    await expect.poll(() => contextQueries.at(-1)).toBe('randonnée');
    const use = section.getByRole('switch', { name: 'Autoriser', exact: true });
    await use.focus();
    await page.keyboard.press('Space');
    await expect(use).not.toBeChecked();
    await expect(section.locator('span').filter({ hasText: /^Non utilisable$/ })).toBeVisible();
    await expectNoOverflow(page, `discussions-${width}-${theme}`);
    const scan = await scanPage(page, testInfo, `discussions-${width}-${theme}`);
    expect(scan.blocking, scan.summary).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(`discussions-${width}-${theme}.png`),
      fullPage: true,
    });
    await section.getByRole('button', { name: 'Purger tout le contexte', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog.getByText('Éléments concernés, dépendances comprises : 1')).toBeVisible();
    await dialog.getByRole('button', { name: 'Confirmer la purge', exact: true }).click();
    await expect(
      section.getByText('Un rendez-vous prévu pour préparer une randonnée.')
    ).toHaveCount(0);
    await expect(
      section.getByRole('button', { name: 'Remettre en utilisation', exact: true })
    ).toBeVisible();
    expect(writes).toHaveLength(2);
    budgetConfigured = false;
    await page.reload();
    await openContextPanels(section);
    const rebuild = section.getByRole('button', { name: 'Reconstruire le contexte', exact: true });
    await rebuild.focus();
    await page.keyboard.press('Space');
    await expect.poll(() => writes.length).toBe(3);
    await expect(
      section.getByText(/^Reconstruction bloquée : les plafonds de coût LLM/)
    ).toBeVisible();
    await expect(section.getByText(/^La demande est enregistrée\./)).toHaveCount(0);
    await expect(rebuild).toBeFocused();
    await expectNoOverflow(page, `discussions-budget-blocked-${width}`);
    expect(pageErrors).toEqual([]);
  });
}

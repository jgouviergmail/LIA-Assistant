/**
 * A skill's life in the settings (lot 14), in a real browser.
 *
 * - **The unused skills are proposed before any fold is opened**, by name, and
 *   the answer sends exactly the skills shown — switched off by a click, or
 *   kept by the keyboard alone.
 * - **The way back is asked first**: « Restore the previous version » opens a
 *   confirmation; only « Restore » sends, and the list is read again so the
 *   screen shows the new way back.
 * - **The proposal fits a 320 px phone** without a horizontal scroll.
 *
 * The oracle is what is ASKED of the server and what the page says, never a
 * class name.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

/** Mirrors `AppConfig` with the skills switch ON. */
const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
  features: {
    tool_approval_enabled: false,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_embedding_model: 'text-embedding-3-small',
    journals_enabled: false,
    skills_enabled: true,
    skill_library_enabled: false,
  },
  capabilities: { skills: { enabled: true, family: 'reach' } },
  api_version: 'v1',
};

const COUNTED = '2026-11-13T09:00:00Z';

/** Mirrors one item of `GET /skills` (skills/router.py::list_skills). */
function skill(name: string, over: Record<string, unknown> = {}) {
  return {
    name,
    description: `${name} for the journey.`,
    descriptions: null,
    scope: 'user',
    category: null,
    priority: 50,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    admin_enabled: true,
    dialogue: false,
    outputs: null,
    skill_id: `id-${name}`,
    provenance: 'authored',
    is_third_party: false,
    shared_origin: null,
    shared_with: [],
    use_count: 0,
    last_used_at: null,
    counted_since: COUNTED,
    dormant: false,
    previous_version_at: null,
    ...over,
  };
}

function listing(skills: unknown[]) {
  return { skills, total: skills.length, dormant_after_days: 60 };
}

const TWO_ASLEEP = listing([
  skill('idle-one', { dormant: true }),
  skill('idle-two', { dormant: true }),
  skill('daily', { use_count: 3, last_used_at: '2026-12-01T09:00:00Z' }),
]);

function base(list: unknown): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/skills', method: 'GET', json: list },
    { url: '**/api/v1/plugins', method: 'GET', json: { plugins: [], total: 0 } },
  ];
}

function answering(sent: unknown[], settled: string[]): MockRoute {
  return {
    url: '**/api/v1/skills/dormant-decision',
    method: 'POST',
    handler: async route => {
      const body = route.request().postDataJSON() as { decision: string };
      sent.push(body);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ decision: body.decision, settled }),
      });
    },
  };
}

test.describe("a skill's life", () => {
  test('the unused skills are proposed by name and switched off as shown', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent: unknown[] = [];
    await authenticate({ language: 'en' });
    await mockApi([...base(TWO_ASLEEP), answering(sent, ['idle-one', 'idle-two'])]);
    await page.goto('/en/dashboard/settings?section=skills');

    const notice = page.getByRole('region', { name: 'Skills you no longer use' });
    await expect(notice).toBeVisible({ timeout: 20_000 });
    await expect(notice.getByRole('listitem')).toHaveText(['idle-one', 'idle-two']);
    expect(sent).toEqual([]);

    await notice.getByRole('button', { name: 'Switch them off' }).click();

    await expect.poll(() => sent.length, { timeout: 10_000 }).toBe(1);
    expect(sent[0]).toEqual({ skill_ids: ['id-idle-one', 'id-idle-two'], decision: 'switch_off' });
    await expect(page.getByText('2 skills switched off')).toBeVisible();
    await expect(notice).toBeHidden();
  });

  test('keeping them takes the keyboard alone, and the card says how often a skill served', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent: unknown[] = [];
    await authenticate({ language: 'en' });
    await mockApi([...base(TWO_ASLEEP), answering(sent, ['idle-one', 'idle-two'])]);
    await page.goto('/en/dashboard/settings?section=skills');

    const keep = page.getByRole('button', { name: 'Keep them' });
    await expect(keep).toBeVisible({ timeout: 20_000 });
    await keep.focus();
    await page.keyboard.press('Enter');

    await expect.poll(() => sent.length, { timeout: 10_000 }).toBe(1);
    expect(sent[0]).toEqual({ skill_ids: ['id-idle-one', 'id-idle-two'], decision: 'keep' });
    await expect(
      page.getByText('Kept: LIA will ask again if they go unused for another 60 days')
    ).toBeVisible();

    await page.getByText('My imported skills').click();
    await expect(
      page.getByText('Used 3 times since Nov 13, 2026, last on Dec 1, 2026')
    ).toBeVisible();
    await expect(page.getByText('No use recorded since Nov 13, 2026')).toHaveCount(2);
  });

  test('the previous version comes back only once the person confirms', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const restores: string[] = [];
    let reads = 0;
    await authenticate({ language: 'en' });
    await mockApi([
      { url: '**/api/v1/config', json: APP_CONFIG },
      {
        url: '**/api/v1/skills',
        method: 'GET',
        handler: async route => {
          reads += 1;
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(
              listing([skill('notes', { previous_version_at: '2026-11-12T08:00:00Z' })])
            ),
          });
        },
      },
      { url: '**/api/v1/plugins', method: 'GET', json: { plugins: [], total: 0 } },
      {
        url: '**/api/v1/skills/notes/restore-previous',
        method: 'POST',
        handler: async route => {
          restores.push(route.request().url());
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(skill('notes')),
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=skills');
    await page.getByText('My imported skills').click({ timeout: 20_000 });
    await page.getByRole('button', { name: 'Skill details: notes' }).click();

    await expect(page.getByText('Previous version kept, replaced on Nov 12, 2026')).toBeVisible();
    await page.getByRole('button', { name: 'Restore the previous version' }).click();
    const confirm = page.getByRole('alertdialog', { name: 'Restore the previous version?' });
    await expect(confirm).toBeVisible();
    expect(restores).toEqual([]);
    const readsBefore = reads;

    await confirm.getByRole('button', { name: 'Restore', exact: true }).click();

    await expect.poll(() => restores.length, { timeout: 10_000 }).toBe(1);
    await expect(page.getByText('Previous version of notes restored')).toBeVisible();
    await expect.poll(() => reads, { timeout: 10_000 }).toBeGreaterThan(readsBefore);
  });

  test('the proposal and the way back pass axe', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate({ language: 'en' });
    await mockApi(
      base(
        listing([
          skill('idle-one', { dormant: true }),
          skill('notes', { previous_version_at: '2026-11-12T08:00:00Z' }),
        ])
      )
    );
    await page.goto('/en/dashboard/settings?section=skills');
    await expect(page.getByRole('region', { name: 'Skills you no longer use' })).toBeVisible({
      timeout: 20_000,
    });

    const onPage = await scanPage(page, testInfo, '/dashboard/settings#skills (proposal)');
    expect(
      onPage.blocking,
      `axe violations, skills with the proposal:\n${onPage.summary}`
    ).toHaveLength(0);

    await page.getByText('My imported skills').click();
    await page.getByRole('button', { name: 'Skill details: notes' }).click();
    await expect(page.getByRole('button', { name: 'Restore the previous version' })).toBeVisible();
    const sheet = await scanPage(
      page,
      testInfo,
      '/dashboard/settings#skills (detail sheet)',
      '[role="dialog"]'
    );
    expect(sheet.blocking, `axe violations, the detail sheet:\n${sheet.summary}`).toHaveLength(0);
  });

  test('the proposal fits a 320 px phone', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'en' });
    await mockApi(base(TWO_ASLEEP));
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/en/dashboard/settings?section=skills');
    await awaitStyledPage(page, '/dashboard/settings?section=skills @320px');
    await expect(page.getByRole('region', { name: 'Skills you no longer use' })).toBeVisible();

    await expectNoOverflow(page, 'unused-skills proposal @320px');
  });
});

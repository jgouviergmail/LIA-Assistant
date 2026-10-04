/**
 * Finding a skill and installing it from its repository (ADR-327), in a real browser.
 *
 * Three claims only a laid-out page proves:
 *
 * - **Nothing is installed before it is read.** « Find skills » searches the
 *   portal, « Read » shows the skill — with the sentence saying what a skill
 *   written elsewhere may do here, in real English — and only « Install »
 *   writes, sending back the COMMIT the preview read (the oracle is what is
 *   ASKED, which survives a refactor of the gesture).
 * - **An audit's refusal holds.** A skill the instance refuses stays readable,
 *   its « Install » says why, and a click sends nothing.
 * - **The dialog fits a 320 px phone** with the preview open, without a
 *   horizontal scroll.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const SHA = 'a'.repeat(40);

/** Mirrors `AppConfig` with both switches the library needs ON. */
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
    skill_library_enabled: true,
  },
  capabilities: {
    skills: { enabled: true, family: 'reach' },
    skill_library: { enabled: true, family: 'reach' },
  },
  api_version: 'v1',
};

/** Mirrors `LibrarySearchResponse` (skill_library/schemas.py). */
const SEARCH = {
  portal: 'skills_sh',
  query_max_chars: 100,
  items: [
    {
      registry_id: 'acme/skills/pdf-tools',
      name: 'pdf-tools',
      source: 'acme/skills',
      skill_id: 'pdf-tools',
      installs: 1234,
      repository: 'acme/skills',
      supported: true,
      installed: false,
    },
  ],
};

/** Mirrors `LibraryPreviewResponse`. */
function preview(over: Record<string, unknown> = {}) {
  return {
    portal: 'skills_sh',
    registry_id: 'acme/skills/pdf-tools',
    repository: 'acme/skills',
    ref: 'HEAD',
    path: 'skills/pdf-tools',
    commit_sha: SHA,
    tree_sha: 'b'.repeat(40),
    name: 'pdf-tools',
    description: 'Extracts tables and text from PDF files.',
    files: [
      { path: 'SKILL.md', size: 2048 },
      { path: 'scripts/extract_tables_from_a_very_long_file_name.py', size: 4096 },
    ],
    skipped: [],
    has_scripts: true,
    audits: [{ provider: 'socket', risk: 'low', alerts: 0 }],
    blocked_by: null,
    conflict: 'none',
    ...over,
  };
}

function routes(previewBody: unknown): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/skills', method: 'GET', json: { skills: [], total: 0 } },
    { url: '**/api/v1/plugins', method: 'GET', json: { plugins: [], total: 0 } },
    { url: '**/api/v1/skill-library/search?*', method: 'GET', json: SEARCH },
    {
      url: '**/api/v1/skill-library/preview?*',
      method: 'GET',
      json: { preview: previewBody, choice: null },
    },
  ];
}

async function openPreview(page: import('@playwright/test').Page) {
  await page.goto('/en/dashboard/settings?section=skills');
  await page.getByRole('button', { name: 'Find skills' }).click({ timeout: 20_000 });
  await page.getByRole('searchbox').fill('pdf');
  await page.getByRole('button', { name: 'Read pdf-tools' }).click({ timeout: 10_000 });
  await expect(page.getByText('Extracts tables and text from PDF files.')).toBeVisible();
}

test.describe('skill library', () => {
  test('a skill is read before it is installed, then installed at the commit read', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const writes: unknown[] = [];
    await authenticate({ language: 'en' });
    await mockApi([
      ...routes(preview()),
      {
        url: '**/api/v1/skill-library/install',
        method: 'POST',
        handler: async route => {
          writes.push(route.request().postDataJSON());
          await route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({ skill_id: 's1', name: 'pdf-tools', commit_sha: SHA }),
          });
        },
      },
    ]);
    await openPreview(page);

    await expect(page.getByText(/Written outside LIA: it runs apart/)).toBeVisible();
    expect(writes).toEqual([]);

    await page.getByRole('button', { name: 'Install' }).click();
    await expect.poll(() => writes.length, { timeout: 10_000 }).toBe(1);
    expect(writes[0]).toMatchObject({
      repository: 'acme/skills',
      path: 'skills/pdf-tools',
      commit_sha: SHA,
      portal: 'skills_sh',
    });
    await expect(page.getByText('pdf-tools is installed.')).toBeVisible();
  });

  test('an audit refusal holds: the reason is said and nothing is sent', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const writes: unknown[] = [];
    await authenticate({ language: 'en' });
    await mockApi([
      ...routes(
        preview({
          blocked_by: 'critical',
          audits: [{ provider: 'socket', risk: 'critical', alerts: 3 }],
        })
      ),
      {
        url: '**/api/v1/skill-library/install',
        method: 'POST',
        handler: async route => {
          writes.push(route.request().postDataJSON());
          await route.fulfill({ status: 201, body: '{}' });
        },
      },
    ]);
    await openPreview(page);

    const install = page.getByRole('button', { name: 'Install' });
    await expect(install).toHaveAttribute('aria-disabled', 'true');
    // Playwright never clicks an `aria-disabled` control; a browser does, and the
    // handler's guard is what must hold — so the click is forced.
    await install.click({ force: true });
    await expect(
      page.getByText('An audit rates this skill critical risk — this instance does not install it.')
    ).toBeVisible();
    expect(writes).toEqual([]);
  });

  test('the dialog fits a 320 px phone with a skill open', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(routes(preview()));
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/en/dashboard/settings?section=skills');
    await awaitStyledPage(page, '/dashboard/settings?section=skills @320px');
    await page.getByRole('button', { name: 'More actions' }).click();
    await page.getByRole('menuitem', { name: 'Find skills' }).click();
    await page.getByRole('searchbox').fill('pdf');
    await page.getByRole('button', { name: 'Read pdf-tools' }).click({ timeout: 10_000 });
    await expect(page.getByText('Extracts tables and text from PDF files.')).toBeVisible();

    await expectNoOverflow(page, 'skill library preview @320px');
  });
});

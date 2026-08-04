/**
 * Accessibility journeys — axe WCAG 2.x A/AA on the high-risk authenticated
 * pages, plus reflow/zoom and keyboard reachability (audit AC-002).
 *
 * Extends the foundation smoke (axe-smoke.spec.ts) to the journeys the audit
 * called out: chat, settings, spaces and the admin screens. Every page is
 * scanned hermetically (mocked API, 501 catch-all) with `color-contrast`
 * blocking, and per-page reports are archived as attachments by `scanPage`.
 *
 * Reflow (WCAG 1.4.10): at 320 CSS px — the 400 % zoom equivalent of a
 * 1280 px layout — the page must not scroll horizontally. The 200 % zoom
 * equivalent (640 px) is scanned with axe as well: DOM-level contrast and
 * naming must survive responsive re-layout.
 *
 * Keyboard: from the page body, Tab must reach visibly-focusable controls —
 * a minimal reachability check complementing the per-component RTL tests.
 */
import { test, expect, briefingCardsMock, type MockRoute } from '../fixtures';
import { relationsData } from '../fixtures/relations';
import { scanPage } from './scan';

// --- Hermetic payloads (mirroring the smoke specs' shapes) -------------------

const assistantMessage = {
  id: '00000000-0000-4000-8000-00000000m001',
  role: 'assistant',
  content: 'Here is your **answer** with a [link](https://example.com/doc).',
  message_metadata: null,
  created_at: '2026-07-15T10:00:00Z',
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
};

const chatData: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me',
    json: {
      id: '00000000-0000-4000-8000-00000000c001',
      user_id: '00000000-0000-4000-8000-000000000001',
      title: 'E2E',
      message_count: 1,
      total_tokens: 0,
      created_at: '2026-07-15T09:00:00Z',
      updated_at: '2026-07-15T10:00:00Z',
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [assistantMessage],
      conversation_id: '00000000-0000-4000-8000-00000000c001',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
];

const spacesData: MockRoute[] = [
  {
    url: '**/api/v1/rag-spaces*',
    json: {
      spaces: [
        {
          id: '00000000-0000-4000-8000-00000000s001',
          name: 'Project docs',
          description: 'Specs and notes',
          is_active: true,
          document_count: 3,
          ready_document_count: 3,
          total_size: 123456,
          created_at: '2026-07-01T09:00:00Z',
          updated_at: '2026-07-14T09:00:00Z',
        },
      ],
      total: 1,
    },
  },
];

const spaceDetailData: MockRoute[] = [
  ...spacesData,
  {
    url: '**/api/v1/rag-spaces/00000000-0000-4000-8000-00000000s001*',
    json: {
      id: '00000000-0000-4000-8000-00000000s001',
      name: 'Project docs',
      description: 'Specs and notes',
      is_active: true,
      document_count: 1,
      ready_document_count: 1,
      total_size: 123456,
      created_at: '2026-07-01T09:00:00Z',
      updated_at: '2026-07-14T09:00:00Z',
      documents: [
        {
          id: '00000000-0000-4000-8000-00000000d001',
          original_filename: 'spec.pdf',
          file_size: 123456,
          content_type: 'application/pdf',
          status: 'ready',
          error_message: null,
          chunk_count: 12,
          embedding_model: 'text-embedding-3-small',
          embedding_tokens: 3400,
          embedding_cost_eur: 0.0004,
          source_type: 'upload',
          drive_file_id: null,
          created_at: '2026-07-01T10:00:00Z',
        },
      ],
      drive_sources: [],
    },
  },
];

const adminData: MockRoute[] = [
  {
    url: '**/api/v1/admin/image-pricing/pricing*',
    json: {
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      entries: [
        {
          id: '9a7c2c46-0000-4000-8000-000000000042',
          provider: 'openai',
          model: 'gpt-image-1',
          quality: 'high',
          size: '1024x1024',
          cost_per_image_usd: '0.1670',
          effective_from: '2026-01-01T00:00:00Z',
          is_active: true,
        },
      ],
    },
  },
];

async function assertNoHorizontalScroll(page: import('@playwright/test').Page) {
  const overflow = await page.evaluate(() => {
    const el = document.scrollingElement ?? document.documentElement;
    return el.scrollWidth - el.clientWidth;
  });
  expect(overflow, 'page must reflow without horizontal scroll').toBeLessThanOrEqual(1);
}

test.describe('accessibility journeys (axe, hermetic)', () => {
  test('chat page scans clean and is keyboard-reachable', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(chatData);
    await page.goto('/en/dashboard/chat');
    await expect(page.getByText('answer')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/chat');
    expect(blocking, `axe violations on /dashboard/chat:\n${summary}`).toHaveLength(0);

    // Keyboard reachability: Tab from the body reaches focusable controls.
    await page.locator('body').press('Tab');
    const focused = page.locator(':focus');
    await expect(focused).toBeVisible();
  });

  test('settings page scans clean', async ({ page, authenticate, mockApi }, testInfo) => {
    await authenticate();
    await mockApi([]);
    await page.goto('/en/dashboard/settings');
    await expect(page.getByRole('main')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/settings');
    expect(blocking, `axe violations on /dashboard/settings:\n${summary}`).toHaveLength(0);
  });

  test('the routines list and its upcoming runs scan clean', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    // The scan above mocks nothing, so `/scheduled-actions` 501s and the
    // section renders empty: the routine rows — and the two coloured markers
    // the upcoming-runs preview introduced, a 70%-opacity zone name and a
    // clock-change warning — have never been contrast-checked.
    //
    // The two instants below straddle the end of summer time in Paris: same
    // wall clock, different offset, which is exactly when the warning renders.
    await authenticate();
    await mockApi([
      {
        url: '**/api/v1/scheduled-actions**',
        json: {
          // `scheduled_actions`, not `actions`: the hook reads
          // `listData?.scheduled_actions ?? []`, so a wrong key here yields an
          // empty list that looks exactly like a working mock.
          scheduled_actions: [
            {
              id: '00000000-0000-4000-8000-00000000ac01',
              user_id: '00000000-0000-4000-8000-000000000001',
              title: 'Revue du matin',
              action_prompt: 'Résume ma journée',
              days_of_week: [1, 2, 3, 4, 5],
              trigger_hour: 8,
              trigger_minute: 0,
              user_timezone: 'Europe/Paris',
              trigger_kind: 'time',
              condition_config: null,
              requires_approval: false,
              next_trigger_at: '2026-10-24T06:00:00Z',
              is_enabled: true,
              status: 'active',
              last_executed_at: '2026-10-23T06:00:00Z',
              execution_count: 12,
              consecutive_failures: 0,
              last_error: null,
              created_at: '2026-08-01T10:00:00Z',
              updated_at: '2026-08-01T10:00:00Z',
              schedule_display: '',
              next_occurrences: ['2026-10-24T06:00:00Z', '2026-10-26T07:00:00Z'],
            },
          ],
          total: 1,
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=scheduled-actions');
    await expect(page.getByText('Revue du matin')).toBeVisible({ timeout: 20_000 });
    // The later occurrences — and the clock-change marker they carry — fold
    // behind the per-card "Details" disclosure since ADR-208 (the visible line
    // is the next run, zone-stamped). Open it: the scan then covers the folded
    // content too, and the marker must actually be on screen, or this scans a
    // page that happens not to contain the thing it was written for.
    await page.locator('summary').filter({ hasText: 'Details' }).first().click();
    await expect(page.getByText('(clocks change)', { exact: false }).first()).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/settings#routines');
    expect(
      blocking,
      `axe violations on the routines list:
${summary}`
    ).toHaveLength(0);
  });

  test('settings search results scan clean', async ({ page, authenticate, mockApi }, testInfo) => {
    // The listbox exists only while a query is typed, so the scan above never
    // sees it: an unlabelled listbox, an option without a name or a `mark` with
    // insufficient contrast would all pass unnoticed.
    await authenticate();
    await mockApi([]);
    await page.goto('/en/dashboard/settings');
    await expect(page.getByRole('main')).toBeVisible();

    const search = page.getByRole('combobox', { name: 'Search a setting' });
    await expect(search).toBeVisible({ timeout: 20_000 });
    await search.fill('memory');
    await expect(page.getByRole('listbox')).toBeVisible({ timeout: 10_000 });

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/settings#search');
    expect(blocking, `axe violations on the settings search popup:\n${summary}`).toHaveLength(0);
  });

  test('spaces page scans clean', async ({ page, authenticate, mockApi }, testInfo) => {
    await authenticate();
    await mockApi(spacesData);
    await page.goto('/en/dashboard/spaces');
    await expect(page.getByText('Project docs')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/spaces');
    expect(blocking, `axe violations on /dashboard/spaces:\n${summary}`).toHaveLength(0);
  });

  test('relations overview and 360° detail scan clean', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(relationsData);
    await page.goto('/en/dashboard/relations');
    await expect(page.getByText('Gérard Dupont')).toBeVisible();

    // The toolbar only exists past the threshold — assert it is really on
    // screen, or the scan would quietly cover a page without its controls.
    await expect(page.getByRole('combobox')).toBeVisible();

    const overview = await scanPage(page, testInfo, '/dashboard/relations');
    expect(
      overview.blocking,
      `axe violations on /dashboard/relations:\n${overview.summary}`
    ).toHaveLength(0);

    // The 360° detail is client state, not a route — scan it as its own page.
    await page.getByRole('button', { name: /^Gérard Dupont/ }).click();
    // Sections start FOLDED (a compact index): open every one, so the scan
    // covers the rows and pills inside, not just the eight headings. The
    // provider sections are a second, slower query — waiting for their
    // heading is what proves they landed before the scan.
    await expect(page.getByRole('heading', { name: 'Contact card' })).toBeVisible();
    // Clicking a collapsed toggle removes it from this set, so the first one
    // is always the next to open. Bounded: a runaway loop must fail the test,
    // not hang it.
    //
    // Scoped to `main`: the HEADER carries its own `aria-expanded` menus
    // (personality, language), and an unscoped set made the loop open a menu,
    // close it on the next click, and never converge.
    const collapsed = page.getByRole('main').getByRole('button', { expanded: false });
    for (let guard = 0; guard < 20 && (await collapsed.count()) > 0; guard += 1) {
      await collapsed.first().click();
    }
    expect(await collapsed.count()).toBe(0);
    await expect(page.getByText(/sera en retard/)).toBeVisible();
    await expect(page.getByText('Menuiserie Dupont')).toBeVisible();

    const detail = await scanPage(page, testInfo, '/dashboard/relations#detail');
    expect(
      detail.blocking,
      `axe violations on the relations 360° detail:\n${detail.summary}`
    ).toHaveLength(0);
  });

  test('relations detail reflows at 320 CSS px without horizontal scroll', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(relationsData);
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto('/en/dashboard/relations');
    await expect(page.getByText('Gérard Dupont')).toBeVisible();
    await assertNoHorizontalScroll(page);

    // The section heading carries a title, a count pill AND the reply button:
    // the row that is most likely to overflow on the narrowest supported width.
    await page.getByRole('button', { name: /^Gérard Dupont/ }).click();
    // The FOLDED panel first: every section is a heading row here, and a
    // heading row is what overflows. Its content is asserted below, once
    // opened — asserting it now would be asserting a folded section is visible.
    await expect(page.getByRole('heading', { level: 2, name: 'Gérard Dupont' })).toBeVisible();
    await assertNoHorizontalScroll(page);

    // Then OPEN everything. The contact card is the widest content on the
    // page — a postal address that must wrap on its spaces and a URL that
    // cannot wrap at all — and it is folded by default, so a check that
    // stopped here would never have looked at it.
    //
    // Scoped to `main`: the header's own `aria-expanded` menus (personality,
    // language) would otherwise make this loop open and close a menu forever.
    const collapsed = page.getByRole('main').getByRole('button', { expanded: false });
    for (let guard = 0; guard < 20 && (await collapsed.count()) > 0; guard += 1) {
      await collapsed.first().click();
    }
    expect(await collapsed.count()).toBe(0);
    await expect(page.getByText(/sera en retard/)).toBeVisible();
    await expect(page.getByText(/Lilas Blancs/)).toBeVisible();
    await assertNoHorizontalScroll(page);
  });

  test('the dashboard home scans clean and reflows at 320 CSS px', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    // The dashboard grew a results block (four tiles), a Consumption
    // disclosure and a visible avatar picker. The four-up tile row is exactly
    // the kind of grid that reflows badly: at 320 px it must be one column,
    // not four 70 px columns pushed off the side.
    await authenticate();
    await mockApi([
      briefingCardsMock,
      {
        url: '**/api/v1/briefing/synthesis',
        json: {
          greeting: { text: 'Welcome back', generated_at: null, usage: null },
          synthesis: null,
        },
      },
      {
        url: '**/api/v1/product/me/results',
        json: {
          useful_results: 12,
          actions: 5,
          automations: 3,
          commitments_closed: 2,
          cycle_start: '2026-07-15T00:00:00Z',
          measured: true,
        },
      },
      { url: '**/api/v1/usage/**', json: {} },
    ]);

    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto('/en/dashboard');
    // Something only the real page has: the error boundary keeps <main>.
    await expect(page.getByRole('button', { name: "Switch LIA's avatar" })).toBeVisible();
    await assertNoHorizontalScroll(page);

    // Then OPEN the Consumption disclosure — it is closed by default, so a
    // check that stopped here would never look at the widest numbers on the
    // page (token totals, which do not wrap).
    // The <summary> element itself: `getByText` could land on an inner node,
    // and `getByRole('button')` depends on how the engine maps a disclosure
    // triangle — neither is a stable handle on the thing that toggles.
    await page.locator('summary', { hasText: 'Consumption' }).click();
    await assertNoHorizontalScroll(page);

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard@320');
    expect(
      blocking,
      `axe violations on /dashboard at 320 px:
${summary}`
    ).toHaveLength(0);
  });

  test('space detail page (upload zone) scans clean', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(spaceDetailData);
    await page.goto('/en/dashboard/spaces/00000000-0000-4000-8000-00000000s001');
    await expect(page.getByText('spec.pdf')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/spaces/detail');
    expect(blocking, `axe violations on space detail:\n${summary}`).toHaveLength(0);
  });

  test('admin settings tab scans clean (superuser)', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate({ is_superuser: true });
    await mockApi(adminData);
    await page.goto('/en/dashboard/settings');
    await page.getByRole('tab', { name: 'Administration' }).click();
    await page.getByRole('button', { name: /LLM Image Pricing/ }).click();
    await expect(page.getByRole('cell', { name: 'gpt-image-1' })).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/settings#admin');
    expect(blocking, `axe violations on admin settings:\n${summary}`).toHaveLength(0);
  });

  test('dashboard scans clean in dark mode', async ({ page, authenticate, mockApi }, testInfo) => {
    // next-themes defaults to light; the user choice is persisted in
    // localStorage — seed it before any script runs so the whole page
    // renders with the dark palette (guard-proven, browser-verified here).
    await page.addInitScript(() => window.localStorage.setItem('theme', 'dark'));
    await authenticate();
    await mockApi(chatData);
    await page.goto('/en/dashboard/chat');
    await expect(page.getByText('answer')).toBeVisible();
    await expect(page.locator('html.dark')).toHaveCount(1);

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/chat@dark');
    expect(blocking, `axe violations on /dashboard/chat (dark):\n${summary}`).toHaveLength(0);
  });

  test('login reflows at 320 CSS px (400 % zoom) without horizontal scroll', async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto('/en/login');
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    await assertNoHorizontalScroll(page);
    const { blocking, summary } = await scanPage(page, testInfo, '/login@320px');
    expect(blocking, `axe violations on /login @320px:\n${summary}`).toHaveLength(0);
  });

  test('chat reflows at 320 CSS px and scans clean at 640 px (200 % zoom)', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(chatData);

    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto('/en/dashboard/chat');
    await expect(page.getByText('answer')).toBeVisible();
    await assertNoHorizontalScroll(page);

    await page.setViewportSize({ width: 640, height: 720 });
    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/chat@640px');
    expect(blocking, `axe violations on /dashboard/chat @640px:\n${summary}`).toHaveLength(0);
  });
});

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
import { test, expect, type MockRoute } from '../fixtures';
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

  test('spaces page scans clean', async ({ page, authenticate, mockApi }, testInfo) => {
    await authenticate();
    await mockApi(spacesData);
    await page.goto('/en/dashboard/spaces');
    await expect(page.getByText('Project docs')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard/spaces');
    expect(blocking, `axe violations on /dashboard/spaces:\n${summary}`).toHaveLength(0);
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

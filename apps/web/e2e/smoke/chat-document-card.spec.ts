/**
 * Chat journey — generated document cards (ADR-226).
 *
 * Hermetic: the conversation history is mocked with one assistant message
 * carrying two `generated_documents` entries (csv + pdf) in its metadata,
 * everything else dies on the 501 catch-all. Proves, in a real browser
 * accessibility tree, that each card exposes a NAMED native link — the csv
 * as a download (`download` attribute), the pdf opening in a new tab (the
 * API serves application/pdf inline) — and that the link is keyboard
 * reachable.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const assistantMessage = {
  id: '00000000-0000-4000-8000-00000000m001',
  role: 'assistant',
  content: 'Voici votre document.',
  message_metadata: {
    generated_documents: [
      {
        url: '/api/v1/attachments/00000000-0000-4000-8000-00000000d001',
        filename: 'modeles-llm.csv',
        doc_type: 'csv',
        size_bytes: 2048,
        expires_at: null,
      },
      {
        url: '/api/v1/attachments/00000000-0000-4000-8000-00000000d002',
        filename: 'rapport.pdf',
        doc_type: 'pdf',
        size_bytes: 40960,
        expires_at: null,
      },
    ],
  },
  created_at: '2026-08-17T10:00:00Z',
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
      created_at: '2026-08-17T09:00:00Z',
      updated_at: '2026-08-17T10:00:00Z',
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
  {
    url: '**/api/v1/agents/health',
    json: { status: 'healthy', graph_compiled: true },
  },
];

test.describe('chat generated document cards', () => {
  test('cards expose named, keyboard-reachable links (download vs open-in-tab)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatData);

    await page.goto('/en/dashboard/chat', { waitUntil: 'domcontentloaded' });

    // Both cards render with their filenames visible.
    await expect(page.getByText('modeles-llm.csv')).toBeVisible();
    await expect(page.getByText('rapport.pdf')).toBeVisible();
    await expect(page.getByTestId('generated-document-card')).toHaveCount(2);

    // The csv card body OPENS the document viewer page in a new tab.
    const openCsv = page.getByRole('link', { name: 'Open modeles-llm.csv' });
    await expect(openCsv).toBeVisible();
    await expect(openCsv).toHaveAttribute('target', '_blank');
    const viewerHref = await openCsv.getAttribute('href');
    expect(viewerHref).toContain('/dashboard/documents/00000000-0000-4000-8000-00000000d001?');
    expect(viewerHref).toContain('type=csv');

    // A sibling NAMED link downloads the file directly.
    // The href ENDS with the wire path rather than equalling it: `apiResourceUrl`
    // deliberately resolves against `NEXT_PUBLIC_API_URL` when one is configured
    // (the dev API serves HTTPS only, and a Next rewrite refuses its self-signed
    // certificate), so pinning the relative form made this case pass only where
    // no API origin is set. What the rule guarantees is the resource it points at.
    const download = page.getByRole('link', { name: 'Download modeles-llm.csv' });
    await expect(download).toBeVisible();
    await expect(download).toHaveAttribute(
      'href',
      /\/api\/v1\/attachments\/00000000-0000-4000-8000-00000000d001$/
    );
    await expect(download).toHaveAttribute('download', 'modeles-llm.csv');

    // The pdf card opens its inline URL directly (native browser viewer).
    const open = page.getByRole('link', { name: 'Open rapport.pdf' });
    await expect(open).toBeVisible();
    await expect(open).toHaveAttribute('target', '_blank');
    await expect(open).toHaveAttribute(
      'href',
      /\/api\/v1\/attachments\/00000000-0000-4000-8000-00000000d002$/
    );

    // Keyboard reachability: the link takes focus like any native anchor.
    await download.focus();
    await expect(download).toBeFocused();
  });
});

for (const sample of [
  { width: 1280, theme: 'light' },
  { width: 390, theme: 'dark' },
  { width: 320, theme: 'oled' },
]) {
  test(`document previews ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 1100 });
    await authenticate();
    const extraDocuments = ['md', 'txt', 'docx', 'xlsx', 'pptx'].map((type, index) => ({
      url: `/api/v1/attachments/00000000-0000-4000-8000-00000000d00${index + 3}`,
      filename: `source.${type}`,
      doc_type: type,
      size_bytes: 2000,
      expires_at: null,
    }));
    const allDocuments = {
      ...assistantMessage,
      message_metadata: {
        generated_documents: [
          ...assistantMessage.message_metadata.generated_documents,
          ...extraDocuments,
        ],
      },
    };
    await mockApi([
      ...chatData,
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [allDocuments],
          conversation_id: '00000000-0000-4000-8000-00000000c001',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
      {
        url: '**/api/v1/attachments/*/preview',
        handler: route =>
          route.fulfill({
            contentType: 'text/plain',
            body: route.request().url().includes('d006')
              ? 'Office column,Value\nReceived workbook,0'
              : 'Received Office or text excerpt',
          }),
      },
      {
        url: '**/api/v1/attachments/*d001/preview',
        handler: route =>
          route.fulfill({
            contentType: 'text/plain',
            body: 'Model,Detail\nSource A,"comma, retained"\nSource B,second',
          }),
      },
      {
        url: '**/api/v1/attachments/*d002/preview',
        handler: route =>
          route.fulfill({
            contentType: 'image/png',
            body: readFileSync(path.join(__dirname, '../fixtures/media/document-preview.png')),
          }),
      },
    ]);
    await page.goto('/en/dashboard/chat', { waitUntil: 'domcontentloaded' });
    await waitForHydration(page);
    await awaitStyledPage(page, 'source document previews');
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
    }, sample.theme);
    await page.mouse.move(sample.width / 2, 500);
    await page.mouse.wheel(0, -3000);
    await page.getByTestId('generated-document-card').first().scrollIntoViewIfNeeded();
    await expect(page.getByRole('cell', { name: 'comma, retained' })).toBeVisible();
    const expand = page.getByRole('button', { name: 'First page of rapport.pdf' });
    const preview = expand.getByRole('img', { name: 'First page of rapport.pdf' });
    await preview.scrollIntoViewIfNeeded();
    await expect(preview).toBeVisible();
    expect(
      await preview.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)
    ).toBe(true);
    await expand.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toBeVisible();
    // The lazy thumbnail can fail after the reader has already opened the dialog.
    await preview.evaluate(image => image.dispatchEvent(new Event('error')));
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const retry = page.getByRole('button', { name: 'Retry', exact: true });
    await expect(retry).toBeFocused();
    await retry.click();
    await expect(preview).toBeVisible();
    await expect
      .poll(() =>
        preview.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)
      )
      .toBe(true);
    for (const card of await page.getByTestId('generated-document-card').all()) {
      await card.scrollIntoViewIfNeeded();
      const height = await card
        .locator('.lia-document-preview')
        .evaluate(node => node.getBoundingClientRect().height);
      expect(height).toBeLessThanOrEqual(220);
      for (const action of await card.getByRole('link').all()) {
        const box = await action.boundingBox();
        expect(box?.height).toBeGreaterThanOrEqual(44);
      }
    }
    await expect(page.getByRole('cell', { name: 'Received workbook' })).toBeAttached();
    await expectNoOverflow(page, 'bounded document previews');
    const accessibility = await new AxeBuilder({ page })
      .include('[data-testid=generated-document-card]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page
      .getByTestId('generated-document-card')
      .first()
      .screenshot({ path: test.info().outputPath(`document-${sample.theme}.png`) });
  });
}

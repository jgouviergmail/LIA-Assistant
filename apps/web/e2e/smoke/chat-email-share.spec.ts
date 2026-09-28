/**
 * Sending a file or an answer by e-mail (ADR-321), in a real browser.
 *
 * Hermetic: the conversation, the send options and the send endpoint are
 * mocked; everything else dies on the 501 catch-all. What only a laid-out,
 * keyboard-driven page proves:
 *
 * 1. **An answer leaves as the file « Download » writes**: the chip opens the
 *    dialog, the person types a recipient and sends; the oracle is what is
 *    ASKED — the answer as Markdown under its dated name, their subject, no
 *    words written in their place.
 * 2. **Without a mailbox, the relay writes to the account itself**: no field
 *    to fill, the address shown, no recipient sent — and a document card sends
 *    its own file by id.
 * 3. **A refusal is said in words** and the dialog stays for another try.
 * 4. **At 320 px the dialog fits**, and it scans clean (axe WCAG A/AA).
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';

const DOC_ID = '4d7c1b2a-9e8f-4a6b-8c5d-2e1f0a9b8c7d';
const DOC_URL = `/api/v1/attachments/${DOC_ID}`;
const FUTURE = '2099-01-01T00:00:00Z';
const ANSWER = 'Here is the plan for Monday.';
/** The document card the answer draws — present once the thread rendered. */
const DOC_CARD = '[data-testid="generated-document-card"]';

const CONFIG: MockRoute = {
  url: '**/api/v1/config',
  json: {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
    features: {
      tool_approval_enabled: false,
      attachments_enabled: true,
      rag_spaces_enabled: false,
      rag_spaces_embedding_model: '',
      email_share_enabled: true,
    },
    api_version: 'v1',
  },
};

const MESSAGE = {
  id: '00000000-0000-4000-8000-00000000e321',
  role: 'assistant',
  content: ANSWER,
  message_metadata: {
    generated_documents: [
      {
        url: DOC_URL,
        filename: 'plan.pdf',
        doc_type: 'pdf',
        size_bytes: 2048,
        expires_at: FUTURE,
      },
    ],
  },
  created_at: '2026-09-25T10:00:00Z',
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
};

function options(route: 'mailbox' | 'relay') {
  return {
    route,
    own_address: route === 'relay' ? 'me@example.com' : null,
    mailbox_needs_reconnect: false,
    max_file_bytes: 3_000_000,
    max_recipients: 10,
    subject_max_chars: 200,
    message_max_chars: 5000,
  };
}

interface Sent {
  bodies: unknown[];
  status: number;
  answer: unknown;
}

function routes(route: 'mailbox' | 'relay', sent: Sent): MockRoute[] {
  return [
    CONFIG,
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [MESSAGE],
        conversation_id: '00000000-0000-4000-8000-0000000000ff',
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/email-share/options', json: options(route) },
    {
      url: '**/api/v1/email-share',
      method: 'POST',
      handler: async request => {
        sent.bodies.push(request.request().postDataJSON());
        await request.fulfill({
          status: sent.status,
          contentType: 'application/json',
          body: JSON.stringify(sent.answer),
        });
      },
    },
  ];
}

function sentOk(route: 'mailbox' | 'relay'): Sent {
  return { bodies: [], status: 200, answer: { route, recipients: 1 } };
}

test.describe('sending a file or an answer by e-mail', () => {
  test('an answer leaves as the Markdown file Download writes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const sent = sentOk('mailbox');
    await mockApi(routes('mailbox', sent));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, DOC_CARD);
    await page.getByRole('button', { name: 'Send by e-mail', exact: true }).first().click();

    const dialog = page.getByRole('dialog', { name: 'Send by e-mail' });
    await expect(dialog).toBeVisible();
    const send = dialog.getByRole('button', { name: 'Send', exact: true });
    await expect(send).toBeDisabled();
    await dialog.getByLabel('To').fill('bob@example.com');
    await send.click();

    await expect.poll(() => sent.bodies.length).toBe(1);
    const body = sent.bodies[0] as {
      recipients: string[];
      subject: string;
      message: string | null;
      attachment: { kind: string; filename: string; text: string };
    };
    expect(body.recipients).toEqual(['bob@example.com']);
    expect(body.subject).toMatch(/^LIA's answer of /);
    expect(body.message).toBeNull();
    expect(body.attachment.kind).toBe('markdown');
    expect(body.attachment.filename).toMatch(/^lia-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}$/);
    expect(body.attachment.text).toContain(ANSWER);
    await expect(page.getByText('E-mail sent to 1 recipient.')).toBeVisible();
    await expect(dialog).toBeHidden();
  });

  test('through the relay a document card sends its file to the account itself', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const sent = sentOk('relay');
    await mockApi(routes('relay', sent));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, DOC_CARD);
    await page.getByRole('button', { name: 'Send plan.pdf by e-mail' }).click();

    const dialog = page.getByRole('dialog', { name: 'Send by e-mail' });
    await expect(dialog.getByText('To: me@example.com (your own address)')).toBeVisible();
    await expect(dialog.getByLabel('To')).toHaveCount(0);
    await dialog.getByRole('button', { name: 'Send', exact: true }).click();

    await expect.poll(() => sent.bodies.length).toBe(1);
    expect(sent.bodies[0]).toMatchObject({
      recipients: [],
      subject: 'plan.pdf',
      attachment: { kind: 'file', attachment_id: DOC_ID },
    });
    await expect(page.getByText('E-mail sent to your address.')).toBeVisible();
  });

  test('a refusal is said in words and the dialog stays', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const sent: Sent = {
      bodies: [],
      status: 409,
      answer: { detail: { code: 'email_share_mailbox_reconnect' } },
    };
    await mockApi(routes('mailbox', sent));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, DOC_CARD);
    await page.getByRole('button', { name: 'Send plan.pdf by e-mail' }).click();
    const dialog = page.getByRole('dialog', { name: 'Send by e-mail' });
    await dialog.getByLabel('To').fill('bob@example.com');
    await dialog.getByRole('button', { name: 'Send', exact: true }).click();

    await expect(page.getByText(/Your mailbox connection expired: reconnect it in/)).toBeVisible();
    await expect(dialog).toBeVisible();
  });

  test('at 320 px the dialog stays on the screen and scans clean', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await authenticate();
    await mockApi(routes('mailbox', sentOk('mailbox')));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, DOC_CARD);
    await page.getByRole('button', { name: 'Send plan.pdf by e-mail' }).click();
    const dialog = page.getByRole('dialog', { name: 'Send by e-mail' });
    await expect(dialog.getByLabel('To')).toBeVisible();

    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    const scrolls = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(scrolls).toBe(false);

    const { blocking, summary } = await scanPage(page, testInfo, 'chat email share dialog');
    expect(blocking, `axe violations on the e-mail dialog:\n${summary}`).toHaveLength(0);
  });
});

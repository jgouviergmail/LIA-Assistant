/**
 * Clickable FAQ examples (W1) — the written phrase becomes a real intent.
 *
 * The FAQ holds ~375 ready-made instructions per language, authored and
 * translated six times: the best onboarding material of the product, rendered
 * as inert italics nobody could act on. Reading "Trouve le contact de Jean"
 * meant switching to the chat and retyping it from memory.
 *
 * Unit tests prove the split and the wiring. Only a browser proves the chain
 * end to end, and above all the part that would be a betrayal if it broke:
 * clicking an example NEVER sends anything. It prefills. The user reads the
 * phrase in the composer, edits it if they want, and decides.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CHAT: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
      total_count: 0,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('a FAQ example opens the chat, prefilled', () => {
  test('clicking an example lands the exact phrase in the composer', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(CHAT);
    await page.goto('/fr/dashboard/faq');

    // Question triggers are the accordion buttons inside an <h3> — a
    // STRUCTURAL handle. Addressing them by wording would tie this guard to
    // editorial content, and a broader button selector would sweep in the
    // header controls (including "Déconnexion").
    const questions = page.locator('h3 button');
    await expect(questions.first()).toBeVisible({ timeout: 30_000 });

    // Answers are collapsed on arrival, and Radix keeps a single one open, so
    // each has to be opened and checked in turn. Not every answer carries a
    // bulleted command; walk until one surfaces.
    const example = page.getByRole('button', { name: /Essayer cet exemple/ }).first();
    const toProbe = Math.min(await questions.count(), 15);
    for (let i = 0; i < toProbe; i += 1) {
      await questions.nth(i).click();
      if (await example.count()) break;
    }

    await expect(example, 'the FAQ must offer at least one actionable example').toBeVisible({
      timeout: 15_000,
    });

    // The accessible name carries the phrase; capture it to compare with what
    // actually reaches the composer.
    const label = (await example.getAttribute('aria-label')) ?? '';
    const phrase = label.replace(/^[^:]*:\s*/, '').trim();
    expect(phrase.length, 'the example must carry a real phrase').toBeGreaterThan(3);

    await example.click();

    await page.waitForURL(/\/dashboard\/chat/, { timeout: 15_000 });
    const composer = page.getByRole('textbox').first();
    await expect(composer).toHaveValue(phrase, { timeout: 15_000 });
  });

  test('never sends the message on its own', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });

    // Any call to the streaming endpoint is a failure of the contract.
    let sent = 0;
    await page.route('**/api/v1/agents/chat/stream**', route => {
      sent += 1;
      return route.fulfill({ status: 200, body: '' });
    });
    await mockApi(CHAT);

    // Enter through the deep link the FAQ builds, which is what the click does.
    const phrase = 'Trouve le contact de Jean';
    await page.goto(`/fr/dashboard/chat?draft=${encodeURIComponent(phrase)}`);

    const composer = page.getByRole('textbox').first();
    await expect(composer).toHaveValue(phrase, { timeout: 15_000 });

    // Give a spurious auto-send time to happen before concluding it does not.
    await page.waitForTimeout(1_500);
    expect(sent, 'a prefilled draft must never be auto-sent').toBe(0);

    // And nothing is posted as a user message either.
    await expect(page.getByRole('article')).toHaveCount(0);
  });
});

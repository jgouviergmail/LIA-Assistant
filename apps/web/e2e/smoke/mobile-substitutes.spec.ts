/**
 * Mobile substitutes exist (S7) — the doctrine, checked against the DOM.
 *
 * `lib/mobile-visibility` classifies each conditional surface and, for the
 * `substituted` ones, names what replaces it below its threshold. Unit tests
 * keep that table internally consistent and aligned with the Tailwind variants
 * in the source — but a table cannot prove that the replacement actually
 * RENDERS. A substitute that was renamed, moved or dropped would leave the
 * table happily describing a fallback nobody can reach.
 *
 * This spec closes that gap for the surfaces of the chat and the dashboard
 * header: below the threshold the full form is gone AND the substitute is
 * present, above it the full form is back. It is the executable half of G2 —
 * "never hide without a way back".
 */
import { test, expect, type MockRoute } from '../fixtures';

const ROUTES: MockRoute[] = [
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
  {
    url: '**/api/v1/conversations/me/totals',
    json: {
      context_tokens: 68000,
      context_threshold: 100000,
      total_tokens_in: 1,
      total_tokens_out: 1,
    },
  },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('mobile substitutes', () => {
  /** `chat-search-field`: inline field ≥880 px, 🔍 toggle below. */
  test('the chat search field is replaced by a toggle below 880 px', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });

    const field = page.getByRole('searchbox', { name: 'Rechercher...' });
    const toggle = page.getByRole('button', { name: "Rechercher dans l'historique" });

    await page.setViewportSize({ width: 390, height: 800 });
    await expect(toggle, 'the toggle must take over below 880 px').toBeVisible();
    await expect(field).toBeHidden();

    await page.setViewportSize({ width: 1024, height: 800 });
    await expect(field, 'the inline field must come back above 880 px').toBeVisible();
  });

  /** `chat-reset-label`: the destructive action keeps its accessible name. */
  test('the reset action keeps its name when its label steps aside', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });

    for (const width of [320, 1280] as const) {
      await page.setViewportSize({ width, height: 800 });
      // Located BY ITS NAME: if the label were the only source of that name,
      // this query would fail below 640 px.
      await expect(
        page.getByRole('button', { name: 'Supprimer' }),
        `reset must stay named at ${width}px`
      ).toBeVisible();
    }
  });

  /** `header-personality-label` / `header-language-label`. */
  test('the header selectors keep their names when their labels step aside', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await page.locator('header').waitFor({ state: 'visible' });

    for (const width of [320, 768, 1280] as const) {
      await page.setViewportSize({ width, height: 800 });
      const header = page.locator('header');
      // Radix triggers expose aria-label; both must resolve at every width.
      await expect(
        header.getByRole('button', { name: /Personnalité|Chargement/ }),
        `personality selector must stay named at ${width}px`
      ).toBeVisible();
      await expect(
        header.getByRole('button', { name: /Langue/ }),
        `language selector must stay named at ${width}px`
      ).toBeVisible();
    }
  });

  /**
   * The context pill renders at EVERY width (owner arbitration 2026-08-05,
   * v1.27.13): it left the mobile-visibility table when it joined the
   * header's centred group — desktop-only it read as absent on phones, and
   * tap toggles its totals tooltip where hover does not exist.
   */
  test('the context pill stays visible at every width', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });

    const pill = page.getByRole('button', { name: /Contexte de la conversation/ });

    for (const width of [1024, 390, 360] as const) {
      await page.setViewportSize({ width, height: 800 });
      await expect(pill, `the pill must stay visible at ${width}px`).toBeVisible();
    }
  });
});

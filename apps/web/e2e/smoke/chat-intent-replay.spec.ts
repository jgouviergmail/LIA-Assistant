/**
 * A resurrected `?intent=` URL must not re-execute — the FOURTH failure mode
 * of the chat deep links (ADR-210), measured in production on 2026-08-05.
 *
 * Production evidence (v1.27.12, deployed): "Prépare une réponse au mail
 * « Confirmation de votre commande Samsung… »" executed at 06:43:07 and AGAIN
 * at 06:43:34 — two identical rows in `conversation_messages`, each followed
 * by the user typing "Annuler".
 *
 * Why the carrier cannot be cleaned: ADR-192 made deep links real navigations
 * (`window.location.assign`), so the intent URL is a first-class VISIT in the
 * browser's history database. `history.replaceState` rewrites the session
 * ENTRY — the omnibox, a most-visited tile, a session restore or the router's
 * own bookkeeping still hold the original URL and can re-present it as a
 * fresh full load, which re-armed everything and re-sent the request.
 *
 * The fix is idempotence at the CONSUMER: every click mints a one-shot `iid`
 * (`chatIntentHref`) whose consumption lands in a localStorage ledger; a
 * resurrected URL carries a consumed iid and degrades to a visible composer
 * draft. `page.goto` of the same URL twice IS the resurrection — a full
 * document load, exactly what the omnibox or a session restore produces.
 *
 * The no-iid contract is pinned by the second test: backend-emitted intent
 * links ("Run it now" on a proposed scheduled action) are durable and
 * deliberately replayable — each CLICK is a consent.
 */
import { test, expect, chatRoutes, waitForHydration, type ChatBody } from '../fixtures';

const INTENT = 'Réponds au mail de test';
const REPLAY_URL = `/fr/dashboard/chat?intent=${encodeURIComponent(INTENT)}&iid=e2e-replay-0001`;

test.describe('chat intent replay (ADR-210)', () => {
  test('a replayed iid executes once, then degrades to a visible draft', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const bodies: ChatBody[] = [];
    await mockApi(chatRoutes(bodies));

    // First arrival — the click itself. It must execute exactly once.
    await page.goto(REPLAY_URL);
    await waitForHydration(page);
    await expect.poll(() => bodies.length, { timeout: 30_000 }).toBe(1);
    expect(bodies[0].message).toBe(INTENT);

    // Consumption cleans the address bar (rules 2-3, pre-existing contract).
    await page.waitForTimeout(1_000);
    expect(decodeURIComponent(page.url())).not.toContain('intent=');

    // Resurrection: the SAME URL arrives as a new full load — what the
    // omnibox, a most-visited tile or a session restore replays.
    await page.goto(REPLAY_URL);
    await waitForHydration(page);

    // The request becomes a VISIBLE draft: never a send, never a silent drop.
    await expect(page.getByRole('textbox').first()).toHaveValue(INTENT, { timeout: 30_000 });
    expect(bodies).toHaveLength(1);

    // Client-side away-and-back over the poisoned router entry (the ADR-192
    // restore path, prod bundle): still nothing new sent.
    await page.getByRole('navigation').getByRole('link', { name: 'Aide' }).click();
    await page.waitForURL(/\/dashboard\/faq/, { timeout: 30_000 });
    await page.getByRole('navigation').getByRole('link', { name: 'Chat' }).click();
    await page.waitForURL(/\/dashboard\/chat/, { timeout: 30_000 });
    await page.waitForTimeout(1_500);
    expect(bodies).toHaveLength(1);

    // And a reload of the (clean) entry cannot re-execute either.
    await page.reload();
    await waitForHydration(page);
    await page.waitForTimeout(1_500);
    expect(bodies).toHaveLength(1);
  });

  test('an intent WITHOUT iid keeps click-is-consent: every arrival executes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const bodies: ChatBody[] = [];
    await mockApi(chatRoutes(bodies));

    const runItNowUrl = `/fr/dashboard/chat?intent=${encodeURIComponent('Lance la routine')}`;

    await page.goto(runItNowUrl);
    await waitForHydration(page);
    await expect.poll(() => bodies.length, { timeout: 30_000 }).toBe(1);

    // Second click on the same durable notification link, days later.
    await page.goto(runItNowUrl);
    await waitForHydration(page);
    await expect.poll(() => bodies.length, { timeout: 30_000 }).toBe(2);
    expect(bodies[1].message).toBe('Lance la routine');
  });
});

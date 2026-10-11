/**
 * Guided showroom P0 — hermetic behavior oracle (telemetry-OFF build).
 *
 * Runs ONLY in the dedicated clean managed build
 * (`task test:e2e:showroom`): NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided,
 * NEXT_PUBLIC_PRODUCT_TELEMETRY=false, NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0.
 *
 * What must hold:
 * - the complete mission (canonical, edited-email, all-cancel paths) produces
 *   no agent/telemetry request and zero WebSocket. The only permitted API
 *   read, the public demonstrator link, is fulfilled by a local mock;
 * - fonts are served locally and unmocked API calls receive the fixture's 501;
 * - keyboard-only completion works;
 * - with motion allowed the storyboard advances by itself (no Continue);
 * - no horizontal overflow at 320/375/390/768/1024/1280, all six locales at
 *   390 px, light and dark.
 */

import type { Page } from '@playwright/test';

import { expect, test } from '../fixtures';
import { installApiCatchAll, registerRoutes } from '../fixtures/api-mock';
import { installOfflineFonts } from '../fixtures/offline-fonts';

// The public /demo route localizes from Accept-Language: pin the browser to
// French so the role-name selectors below are deterministic (the locale sweep
// navigates explicit prefixes and only uses testids).
test.use({ locale: 'fr-FR' });

const LOCALE_PATHS = ['/demo', '/en/demo', '/de/demo', '/es/demo', '/it/demo', '/zh/demo'];
const DISABLED_DEMO_LINK_MOCK = {
  url: '**/api/v1/product/public-demo-link',
  method: 'GET',
  json: { enabled: false, url: null },
};

test.beforeEach(async ({ mockApi }) => {
  await mockApi([DISABLED_DEMO_LINK_MOCK]);
});

/**
 * The ONE endpoint the mission is allowed to touch, with its reason.
 *
 * `LiveDemoInvitation` asks whether a public demonstrator link is published —
 * a read-only, cookie-less (`credentials: 'omit'`) public read that carries
 * nothing about the visitor, and whose answer the page cannot know otherwise
 * without turning the admin switch into a rebuild. This read is mocked in
 * every test. Everything else stays forbidden: the oracle rejects attempted
 * agent or telemetry calls, even though the API catch-all isolates them.
 *
 * Owner arbitration, 2026-08-08. Exact path only — a prefix would let the
 * surface grow without anyone deciding, which is the mistake ADR-218 was
 * written about.
 */
const ALLOWED_API_PATHS = ['/api/v1/product/public-demo-link'];

/** Collect API requests other than the mocked GET, plus every WebSocket. */
function armNetworkOracle(page: Page): () => string[] {
  const offenders: string[] = [];
  page.on('request', req => {
    const url = req.url();
    if (req.method() === 'GET' && ALLOWED_API_PATHS.some(path => new URL(url).pathname === path))
      return;
    if (url.includes('/api/v1')) offenders.push(`request ${url}`);
  });
  page.on('websocket', ws => {
    offenders.push(`websocket ${ws.url()}`);
  });
  return () => offenders;
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const el = document.scrollingElement!;
    return el.scrollWidth - el.clientWidth;
  });
  expect(overflow, 'document must not scroll horizontally').toBeLessThanOrEqual(0);
}

/** Pick the canonical mission from the picker that now fronts /demo. */
async function pickCanonicalMission(page: Page): Promise<void> {
  await page.getByTestId('showroom-pick-overloaded_morning').click();
}

/** Walk reading + planning with the reduced-motion Continue button. */
async function walkToEmailDecision(page: Page): Promise<void> {
  await pickCanonicalMission(page);
  await page.getByTestId('showroom-start').click();
  for (let i = 0; i < 6; i += 1) {
    await page.getByTestId('showroom-continue').click();
  }
  await expect(page.getByTestId('showroom-decision-0')).toBeVisible();
}

test.describe('guided showroom — hermetic mission', () => {
  test('canonical path: confirm email, refuse calendar, zero API calls', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const offenders = armNetworkOracle(page);
    await page.goto('/demo');

    // Honesty labels are visible before anything starts.
    await expect(page.getByText('Démonstration guidée')).toBeVisible();
    await expect(page.getByText('Données fictives — aucun compte connecté')).toBeVisible();

    await walkToEmailDecision(page);
    await page
      .getByTestId('showroom-decision-0')
      .getByRole('button', { name: 'Confirmer' })
      .click();
    await page.getByTestId('showroom-decision-1').getByRole('button', { name: 'Annuler' }).click();

    const receipt = page.getByTestId('showroom-receipt');
    await expect(receipt).toBeVisible();
    await expect(receipt.getByText(/Envoi de la réponse approuvé/)).toBeVisible();
    await expect(receipt.getByText(/Créneau refusé/)).toBeVisible();
    await expect(
      receipt.getByText(/Aucun appel réel, e-mail ou changement d’agenda/)
    ).toBeVisible();
    await assertNoHorizontalOverflow(page);

    // Proof drawer: opens, links point at GitHub, Escape returns focus.
    await page.getByTestId('showroom-proof-open').click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    const hrefs = await dialog
      .getByRole('link')
      .evaluateAll(links => links.map(l => (l as HTMLAnchorElement).href));
    expect(hrefs.length).toBeGreaterThanOrEqual(6);
    for (const href of hrefs) {
      expect(href.startsWith('https://github.com/jgouviergmail/LIA-Assistant')).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('showroom-proof-open')).toBeFocused();

    expect(offenders(), 'the mission must never call the API').toEqual([]);
  });

  test('edited-email path reaches an honest receipt', async ({ page }) => {
    const offenders = armNetworkOracle(page);
    await page.goto('/demo');
    await walkToEmailDecision(page);
    const emailCard = page.getByTestId('showroom-decision-0');
    await emailCard.getByRole('button', { name: 'Modifier' }).click();
    await emailCard.getByRole('textbox').fill('Propose plutôt 10:00');
    await emailCard.getByRole('button', { name: 'Envoyer les modifications' }).click();
    await page
      .getByTestId('showroom-decision-1')
      .getByRole('button', { name: 'Confirmer' })
      .click();
    await expect(
      page.getByTestId('showroom-receipt').getByText(/Instruction de modification illustrée/)
    ).toBeVisible();
    expect(offenders()).toEqual([]);
  });

  test('all-cancel path shows both refusals as respected outcomes', async ({ page }) => {
    const offenders = armNetworkOracle(page);
    await page.goto('/demo');
    await walkToEmailDecision(page);
    await page.getByTestId('showroom-decision-0').getByRole('button', { name: 'Annuler' }).click();
    await page.getByTestId('showroom-decision-1').getByRole('button', { name: 'Annuler' }).click();
    const receipt = page.getByTestId('showroom-receipt');
    await expect(receipt.getByText(/Envoi refusé/)).toBeVisible();
    await expect(receipt.getByText(/Créneau refusé/)).toBeVisible();
    await expect(receipt.getByText(/Ton refus a été respecté/)).toBeVisible();
    expect(offenders()).toEqual([]);
  });

  test('keyboard-only completion', async ({ page }) => {
    const offenders = armNetworkOracle(page);
    await page.goto('/demo');
    await pickCanonicalMission(page);
    await page.getByTestId('showroom-start').focus();
    await page.keyboard.press('Enter');
    for (let i = 0; i < 6; i += 1) {
      await page.getByTestId('showroom-continue').focus();
      await page.keyboard.press('Enter');
    }
    const confirmEmail = page
      .getByTestId('showroom-decision-0')
      .getByRole('button', { name: 'Confirmer' });
    await confirmEmail.focus();
    await page.keyboard.press('Enter');
    const cancelCalendar = page
      .getByTestId('showroom-decision-1')
      .getByRole('button', { name: 'Annuler' });
    await cancelCalendar.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('showroom-receipt')).toBeVisible();
    expect(offenders()).toEqual([]);
  });

  test('restart replays a full second run', async ({ page }) => {
    await page.goto('/demo');
    await walkToEmailDecision(page);
    await page
      .getByTestId('showroom-decision-0')
      .getByRole('button', { name: 'Confirmer' })
      .click();
    await page
      .getByTestId('showroom-decision-1')
      .getByRole('button', { name: 'Confirmer' })
      .click();
    await page.getByTestId('showroom-restart').click();
    await expect(page.getByTestId('showroom-start')).toBeFocused();
    // Back to the mission's ready screen (NOT the picker): a fresh run walks
    // the whole path again without re-picking.
    await page.getByTestId('showroom-start').click();
    for (let i = 0; i < 6; i += 1) {
      await page.getByTestId('showroom-continue').click();
    }
    await expect(page.getByTestId('showroom-decision-0')).toBeVisible();
  });

  for (const id of ['daily_briefing', 'config_tour']) {
    test(`${id}: informative result without any approval or provider call`, async ({ page }) => {
      const offenders = armNetworkOracle(page);
      await page.goto('/demo');
      await page.getByTestId(`showroom-pick-${id}`).click();
      await page.getByTestId('showroom-start').click();
      for (let i = 0; i < 5; i += 1) await page.getByTestId('showroom-continue').click();
      await expect(page.getByTestId('showroom-receipt')).toBeVisible();
      await expect(page.getByTestId('showroom-decision-0')).toHaveCount(0);
      await expect(page.getByTestId('showroom-rich-response')).not.toContainText(/showroom\./);
      await assertNoHorizontalOverflow(page);
      expect(offenders()).toEqual([]);
    });
  }

  for (const action of ['confirm', 'cancel', 'edit'] as const) {
    test(`phone draft: ${action}, readable mandate and no real call`, async ({ page }) => {
      const offenders = armNetworkOracle(page);
      await page.goto('/demo');
      await page.getByTestId('showroom-pick-phone_booking').click();
      await page.getByTestId('showroom-start').click();
      for (let i = 0; i < 5; i += 1) await page.getByTestId('showroom-continue').click();
      const preview = page.getByTestId('showroom-phone-preview');
      await expect(preview).toContainText('(202) 555-0100');
      await expect(preview).toContainText('Les Jardins');
      await expect(preview).toContainText(
        'Demander une table pour deux jeudi à 20 h, en terrasse si disponible.'
      );
      await expect(preview).toContainText('Ne pas accepter un autre créneau sans me consulter.');
      const card = page.getByTestId('showroom-decision-0');
      if (action === 'edit') {
        await card.getByRole('button', { name: 'Modifier' }).click();
        await card.getByRole('textbox').fill('Demander une table à l’intérieur.');
        await card.getByRole('button', { name: 'Envoyer les modifications' }).click();
        await expect(card.getByRole('note')).toContainText('aucun modèle');
      } else {
        await card
          .getByRole('button', { name: action === 'confirm' ? 'Confirmer' : 'Annuler' })
          .click();
      }
      await expect(page.getByTestId('showroom-receipt')).toBeVisible();
      const response = page.getByTestId('showroom-rich-response');
      if (action === 'confirm') {
        await expect(response).toContainText('Ce résultat est fictif');
      } else {
        await expect(response).not.toContainText('Table intérieure acceptée');
      }
      await assertNoHorizontalOverflow(page);
      expect(offenders()).toEqual([]);
    });
  }
});

test.describe('guided showroom — motion allowed', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' } });

  test('the storyboard advances by itself up to the email decision', async ({ page }) => {
    await page.goto('/demo');
    await pickCanonicalMission(page);
    await page.getByTestId('showroom-start').click();
    await expect(page.getByTestId('showroom-continue')).toHaveCount(0);
    // Pacing budget ≈ 6.3 s — the email card must appear on its own.
    await expect(page.getByTestId('showroom-decision-0')).toBeVisible({
      timeout: 15_000,
    });
  });
});

test.describe('guided showroom — responsive and locales', () => {
  for (const width of [320, 375, 390, 768, 1024, 1280]) {
    test(`no overflow at ${width}px through the canonical path`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/demo');
      await assertNoHorizontalOverflow(page);
      await walkToEmailDecision(page);
      await assertNoHorizontalOverflow(page);
      await page
        .getByTestId('showroom-decision-0')
        .getByRole('button', { name: 'Confirmer' })
        .click();
      await page
        .getByTestId('showroom-decision-1')
        .getByRole('button', { name: 'Annuler' })
        .click();
      await expect(page.getByTestId('showroom-receipt')).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });
  }

  for (const path of LOCALE_PATHS) {
    test(`starts without overflow at 390px on ${path}`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(path);
      await pickCanonicalMission(page);
      await page.getByTestId('showroom-start').click();
      await expect(page.getByTestId('showroom-continue')).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });
  }

  test('light scheme renders the mission without overflow', async ({
    browser,
    apiNetworkGuard,
  }) => {
    const context = await browser.newContext({
      colorScheme: 'light',
      locale: 'fr-FR',
      reducedMotion: 'reduce',
      viewport: { width: 390, height: 844 },
      proxy: apiNetworkGuard.proxy,
    });
    const page = await context.newPage();
    await installOfflineFonts(page);
    await installApiCatchAll(page);
    await registerRoutes(page, [DISABLED_DEMO_LINK_MOCK]);
    const offenders = armNetworkOracle(page);
    await page.goto('/demo');
    await pickCanonicalMission(page);
    await page.getByTestId('showroom-start').click();
    await expect(page.getByTestId('showroom-continue')).toBeVisible();
    await assertNoHorizontalOverflow(page);
    expect(offenders()).toEqual([]);
    await context.close();
  });

  test('German edited receipt stays readable at 320px', async ({ page }) => {
    const offenders = armNetworkOracle(page);
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto('/de/demo');
    await walkToEmailDecision(page);
    const email = page.getByTestId('showroom-decision-0');
    await email.getByRole('button', { name: 'Bearbeiten' }).click();
    await email.getByRole('textbox').fill('Bitte den Preis ausdrücklich bestätigen lassen.');
    await email.getByRole('button', { name: 'Änderungen senden' }).click();
    await page
      .getByTestId('showroom-decision-1')
      .getByRole('button', { name: 'Abbrechen' })
      .click();
    const receipt = page.getByTestId('showroom-receipt');
    await expect(receipt).toBeVisible();
    await expect(receipt).not.toContainText(/showroom\./);
    await assertNoHorizontalOverflow(page);
    const fits = await receipt
      .locator('dd')
      .evaluateAll(nodes => nodes.every(node => node.scrollWidth <= node.clientWidth));
    expect(fits, 'receipt outcomes must wrap rather than clip').toBe(true);
    expect(offenders()).toEqual([]);
  });
});

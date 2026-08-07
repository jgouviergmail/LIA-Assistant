/**
 * Guided showroom P0 — hermetic behavior oracle (telemetry-OFF build).
 *
 * Runs ONLY in the dedicated clean managed build
 * (`task test:e2e:showroom`): NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided,
 * NEXT_PUBLIC_PRODUCT_TELEMETRY=false, NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0.
 *
 * What must hold:
 * - the complete mission (canonical, edited-email, all-cancel paths) produces
 *   ZERO /api/v1 request and zero WebSocket — nothing is mocked on purpose:
 *   an unexpected agent/telemetry call fails loudly;
 * - keyboard-only completion works;
 * - with motion allowed the storyboard advances by itself (no Continue);
 * - no horizontal overflow at 320/375/390/768/1024/1280, all six locales at
 *   390 px, light and dark.
 */

import { expect, test, type Page } from '@playwright/test';

// The public /demo route localizes from Accept-Language: pin the browser to
// French so the role-name selectors below are deterministic (the locale sweep
// navigates explicit prefixes and only uses testids).
test.use({ locale: 'fr-FR' });

const LOCALE_PATHS = ['/demo', '/en/demo', '/de/demo', '/es/demo', '/it/demo', '/zh/demo'];

/** Collect every /api/v1 request + websocket; assert none at the end. */
function armNetworkOracle(page: Page): () => string[] {
  const offenders: string[] = [];
  page.on('request', req => {
    if (req.url().includes('/api/v1')) offenders.push(`request ${req.url()}`);
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
    await expect(receipt.getByText(/Réponse e-mail approuvée/)).toBeVisible();
    await expect(receipt.getByText(/Changement d'agenda refusé/)).toBeVisible();
    await expect(receipt.getByText(/Aucune action externe n'a eu lieu/)).toBeVisible();
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
      page.getByTestId('showroom-receipt').getByText(/Réponse e-mail modifiée/)
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
    await expect(receipt.getByText(/Réponse e-mail refusée/)).toBeVisible();
    await expect(receipt.getByText(/Changement d'agenda refusé/)).toBeVisible();
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
    // Back to the mission's ready screen (NOT the picker): a fresh run walks
    // the whole path again without re-picking.
    await page.getByTestId('showroom-start').click();
    for (let i = 0; i < 6; i += 1) {
      await page.getByTestId('showroom-continue').click();
    }
    await expect(page.getByTestId('showroom-decision-0')).toBeVisible();
  });
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

  test('light scheme renders the mission without overflow', async ({ browser }) => {
    const context = await browser.newContext({
      colorScheme: 'light',
      locale: 'fr-FR',
      reducedMotion: 'reduce',
      viewport: { width: 390, height: 844 },
    });
    const page = await context.newPage();
    await page.goto('/demo');
    await pickCanonicalMission(page);
    await page.getByTestId('showroom-start').click();
    await expect(page.getByTestId('showroom-continue')).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await context.close();
  });
});

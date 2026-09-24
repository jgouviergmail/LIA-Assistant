/**
 * The "Maps" section of the public site (`/maps`), in a real browser.
 *
 * What only a browser proves: the header entry reaches the section, a brick's
 * detail is a real modal (focus in, Escape out, focus back where it was), a
 * journey lights the map up, the history answers its address (`#adr-…`) and its
 * filters, every language serves its own words, and no page scrolls sideways
 * on a phone — the constellation and the chart are wide by design, inside a
 * container the reader swipes, never the page itself.
 *
 * Anonymous pages: the API catch-all (auto fixture) serves the /auth/me 401
 * probe and nothing else is called.
 */

import { test, expect } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

test.describe('maps — reaching the section and reading a map', () => {
  test.use({ viewport: { width: 1280, height: 900 }, locale: 'fr-FR' });

  test('the header entry opens the section, a card opens a map', async ({ page }) => {
    await page.goto('/fr');
    await awaitStyledPage(page, 'landing');
    const header = page.getByRole('banner').or(page.locator('header')).first();
    await header.getByRole('link', { name: 'Cartes' }).click();
    await expect(page).toHaveURL(/\/maps$/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      'Trois cartes pour comprendre'
    );
    await page.getByRole('article').getByRole('link', { name: 'Carte fonctionnelle' }).click();
    await expect(page).toHaveURL(/\/maps\/functional$/);
    await expect(
      page.getByRole('navigation', { name: 'Les cartes de LIA' }).getByRole('link', {
        name: 'Carte fonctionnelle',
      })
    ).toHaveAttribute('aria-current', 'page');
  });

  test('a brick detail is a modal: focus in, Escape out, focus back', async ({ page }) => {
    await page.goto('/maps/functional');
    await awaitStyledPage(page, 'functional map');
    const row = page
      .getByRole('article', { name: /Se souvenir/ })
      .getByRole('button', { name: /^Mémoire long terme/ });
    await row.click();
    const dialog = page.getByRole('dialog', { name: 'Mémoire long terme' });
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(/#f\.memory$/);
    await expect(dialog.getByRole('button', { name: 'Fermer le détail' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(row).toBeFocused();
    await expect(page).not.toHaveURL(/#/);
  });

  test('a journey lights its bricks up, one step at a time', async ({ page }) => {
    await page.goto('/maps/functional');
    await awaitStyledPage(page, 'functional map');
    const journeys = page.getByRole('list', { name: 'Scénarios' });
    await journeys.getByRole('button', { name: 'Une demande devient une action' }).click();
    // The suite runs with reduced motion: the journey waits at its first step
    // for the reader to advance it (autoplay is for the others).
    await expect(page.getByRole('button', { name: 'Lire le parcours' })).toBeVisible();
    await expect(page.getByText('Étape 1 / ')).toBeVisible();
    await page.getByRole('button', { name: 'Étape suivante' }).click();
    await expect(page.getByText('Étape 2 / ')).toBeVisible();
    await expect(page.locator('.lm-constellation .lm-node.is-on')).toHaveCount(1);
    await expect(page.locator('.lm-constellation .lm-flowpath')).toHaveCount(1);
  });

  test('the history answers its address, its filters and its search', async ({ page }) => {
    await page.goto('/maps/history#adr-310');
    await awaitStyledPage(page, 'history');
    const target = page.locator('#adr-310');
    await expect(target).toBeInViewport();
    await expect(target).toHaveClass(/is-target/);

    const all = await page.locator('article.lm-adr-card').count();
    await page
      .getByRole('group', { name: 'Filtrer par thème' })
      .getByRole('button', { name: /^Voix/ })
      .click();
    const voice = await page.locator('article.lm-adr-card').count();
    expect(voice).toBeGreaterThan(0);
    expect(voice).toBeLessThan(all);

    await page.getByRole('button', { name: 'Réinitialiser', exact: true }).click();
    await page.getByRole('searchbox', { name: 'Chercher une décision' }).fill('ADR-001');
    await expect(page.locator('article.lm-adr-card')).toHaveCount(1);
  });

  test('every language serves its own words', async ({ page }) => {
    for (const [path, title] of [
      ['/en/maps', 'Three maps to understand'],
      ['/de/maps/history', 'Die Geschichte von'],
      ['/zh/maps/technical', '如何构建'],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toContainText(title);
    }
  });
});

test.describe('maps — no horizontal overflow on a phone', () => {
  test.use({ viewport: { width: 375, height: 812 }, locale: 'fr-FR' });

  test('every page of the section stays within 375px', async ({ page }) => {
    for (const path of ['/maps', '/maps/functional', '/maps/technical', '/maps/history']) {
      await page.goto(path);
      await awaitStyledPage(page, path);
      await expectNoOverflow(page, `${path} at 375px`);
    }
  });

  test('the detail sheet and the German history stay within 375px', async ({ page }) => {
    await page.goto('/maps/technical#t.langgraph');
    await expect(page.getByRole('dialog')).toBeVisible();
    await expectNoOverflow(page, 'technical detail at 375px');
    await page.goto('/de/maps/history');
    await awaitStyledPage(page, 'history de');
    await expectNoOverflow(page, 'history de at 375px');
  });
});

test.describe('maps — WCAG reflow floor', () => {
  test.use({ viewport: { width: 320, height: 700 }, locale: 'fr-FR' });

  test('the section home and the functional map render at 320px', async ({ page }) => {
    for (const path of ['/maps', '/maps/functional']) {
      await page.goto(path);
      await awaitStyledPage(page, `${path} 320px`);
      await expectNoOverflow(page, `${path} at 320px`);
    }
  });
});

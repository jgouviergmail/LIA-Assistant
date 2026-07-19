import type { Page } from '@playwright/test';

/**
 * Waits until React has hydrated the rendered markup.
 *
 * Why this is needed: a server-rendered page is fully visible, fillable and
 * clickable **before** React attaches its event handlers. Interacting during
 * that window is not a no-op — a `<form>` whose `onSubmit` is not yet attached
 * performs a **native GET submission**, so the click "works" while the
 * application logic never runs. Measured on the dev server (2026-07-19), the
 * login page was still unhydrated after `networkidle` and needed several more
 * seconds; a production build hydrates almost immediately, which is why such a
 * test passes in CI and fails locally — until a slow runner makes it flake
 * there too.
 *
 * There is no public "hydrated" signal in the App Router, so this checks for
 * the React fiber React attaches to the host node. It is an internal name, but
 * a stable one across React 18/19 and far more precise than an arbitrary sleep.
 *
 * @param page - the page under test
 * @param selector - a node inside the hydrated tree (default: the first form)
 */
export async function waitForHydration(page: Page, selector = 'form'): Promise<void> {
  await page.waitForFunction(
    sel => {
      const node = document.querySelector(sel);
      if (!node) return false;
      return Object.keys(node).some(key => key.startsWith('__reactFiber$'));
    },
    selector,
    { timeout: 30_000 }
  );
}

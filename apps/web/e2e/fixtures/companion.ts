import type { Page } from '@playwright/test';

/** Where the person dragged the companion, in viewport percentages (the store's shape). */
export interface CompanionSpot {
  xPct: number;
  yPct: number;
}

/**
 * The person's own gesture: the companion minimized to its restore dot.
 *
 * On a phone nothing but the person moves or folds the companion (ADR-240 §6):
 * at its default spot it may cover a control, and someone reading or tapping
 * underneath minimizes it first — and drags the dot aside when the dot itself
 * sits on what they need (`spot`). A journey that is not about the companion
 * starts from that stored preference, written before the page loads.
 */
export async function minimizeCompanion(page: Page, spot?: CompanionSpot): Promise<void> {
  await page.addInitScript(position => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({
        state: position ? { visible: false, position } : { visible: false },
        version: 0,
      })
    );
  }, spot ?? null);
}

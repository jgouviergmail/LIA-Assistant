import type { Page } from '@playwright/test';

const PREFERENCES_KEY = 'lia_eyes_widget_prefs';

/** The widget's phone breakpoint (`EyesWidget`: `(max-width: 1023px)`). */
const PHONE_MAX_WIDTH = 1023;

/** Where a phone journey's minimized companion waits: the middle of the left edge. */
const PHONE_SPOT = { xPct: 3, yPct: 45 } as const;

/**
 * The person's own gesture: the companion minimized to its restore dot.
 *
 * A journey that is not about the companion and reads a page at any width
 * starts from that stored preference, written before the page loads.
 */
export async function minimizeCompanion(page: Page): Promise<void> {
  await page.addInitScript(key => {
    localStorage.setItem(key, JSON.stringify({ state: { visible: false }, version: 0 }));
  }, PREFERENCES_KEY);
}

/**
 * The companion shown at its default spot, stored as the person's preference:
 * a journey that needs the face on screen on a phone declares it, so the phone
 * default below never applies to it.
 */
export async function showCompanion(page: Page): Promise<void> {
  await page.addInitScript(key => {
    localStorage.setItem(key, JSON.stringify({ state: { visible: true }, version: 0 }));
  }, PREFERENCES_KEY);
}

/**
 * The default every authenticated journey starts from on a phone.
 *
 * Nothing but the person places the companion on a phone (ADR-240 §6): at its
 * default corner the face — or, minimized, its dot — covered a control in ten
 * journeys on 2026-10-17. So unless a spec stored a companion preference of its
 * own (every companion spec does), a phone-sized page starts the way someone who
 * reads and taps would have left it: minimized, the dot dragged to the middle of
 * the left edge. Wider pages are untouched.
 */
export async function minimizeCompanionOnPhones(page: Page): Promise<void> {
  await page.addInitScript(
    ({ key, spot, maxWidth }) => {
      try {
        if (window.innerWidth > maxWidth || localStorage.getItem(key) !== null) return;
        localStorage.setItem(
          key,
          JSON.stringify({ state: { visible: false, position: spot }, version: 0 })
        );
      } catch {
        // An opaque document (about:blank) has no storage: nothing to prepare.
      }
    },
    { key: PREFERENCES_KEY, spot: PHONE_SPOT, maxWidth: PHONE_MAX_WIDTH }
  );
}

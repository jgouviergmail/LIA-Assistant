/**
 * Control-row geometry: every interactive control inside the viewport, none
 * covering another. Shared by the dashboard and chat header reachability specs
 * and by the text-size extremes spec, which re-measures both rows at the
 * smallest and largest interface text size.
 *
 * Document-scroll checks are blind to this class of defect:
 * `html { overflow-x: hidden }` clips a row instead of scrolling the page, and
 * an absolutely positioned control can cover a sibling without producing any
 * overflow at all. The only reliable oracle compares the control boxes.
 */
import type { Page } from '@playwright/test';

/**
 * Which row to measure.
 * - `dashboard-header`: the authenticated shell's `<header>` (links, buttons).
 * - `chat-header`: the chat's own header row, a `div` inside the shell reached
 *   through the shell's sizing class, so the probe breaks loudly if that shell
 *   disappears.
 */
export type ControlRow = 'dashboard-header' | 'chat-header';

export interface ControlProbe {
  clipped: Array<{ name: string; overflowPx: number }>;
  overlaps: string[];
}

/**
 * Measure the row's leaf controls against the viewport and each other.
 *
 * Throws when the row or its visible controls are missing: a probe that finds
 * nothing to measure proves nothing.
 */
export async function probeControls(page: Page, row: ControlRow): Promise<ControlProbe> {
  return page.evaluate(which => {
    const root =
      which === 'dashboard-header'
        ? document.querySelector('header')
        : (document.querySelector('[class*="calc(100vh"]')?.firstElementChild?.firstElementChild
            ?.firstElementChild ?? null);
    const selector = which === 'dashboard-header' ? 'a, button' : 'button, a, input';
    const clipped: Array<{ name: string; overflowPx: number }> = [];
    const overlaps: string[] = [];
    // An absent row or an empty one would make every check pass vacuously.
    if (!root) throw new Error(`control row "${which}" not found`);

    const viewportWidth = document.documentElement.clientWidth;
    const name = (el: Element): string =>
      el.getAttribute('aria-label') ||
      el.getAttribute('title') ||
      (el.textContent ?? '').trim().slice(0, 24) ||
      el.tagName.toLowerCase();

    const controls = Array.from(root.querySelectorAll(selector)).filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    if (controls.length === 0) throw new Error(`control row "${which}" has no visible control`);

    for (const el of controls) {
      const r = el.getBoundingClientRect();
      if (r.right > viewportWidth + 1) {
        clipped.push({
          name: name(el),
          overflowPx: Math.round((r.right - viewportWidth) * 10) / 10,
        });
      }
    }

    for (let i = 0; i < controls.length; i++) {
      for (let j = i + 1; j < controls.length; j++) {
        // Skip nesting (a button inside a link): only siblings can "cover".
        if (controls[i].contains(controls[j]) || controls[j].contains(controls[i])) continue;
        const a = controls[i].getBoundingClientRect();
        const b = controls[j].getBoundingClientRect();
        if (
          a.left < b.right - 1 &&
          b.left < a.right - 1 &&
          a.top < b.bottom - 1 &&
          b.top < a.bottom - 1
        ) {
          overlaps.push(`${name(controls[i])} ×× ${name(controls[j])}`);
        }
      }
    }
    return { clipped, overlaps };
  }, row);
}

/**
 * Wait until the row stops moving before measuring.
 *
 * Several controls settle asynchronously — the personality selector swaps a
 * "loading" placeholder for the emoji + title, the chat pills appear once the
 * totals arrive — and measuring during a swap produced flaky overlaps. Poll the
 * geometry until three consecutive readings agree.
 */
export async function waitForStableControls(page: Page, row: ControlRow): Promise<void> {
  const signature = () =>
    page.evaluate(which => {
      const root =
        which === 'dashboard-header'
          ? document.querySelector('header')
          : document.querySelector('[class*="calc(100vh"]')?.firstElementChild?.firstElementChild
              ?.firstElementChild;
      if (!root) return '';
      const selector = which === 'dashboard-header' ? 'a, button' : 'button, a, input';
      return Array.from(root.querySelectorAll(selector))
        .map(el => {
          const r = el.getBoundingClientRect();
          return `${Math.round(r.x)}:${Math.round(r.width)}`;
        })
        .join('|');
    }, row);

  // A resize reaches the stylesheet's media queries through rendering updates,
  // up to TWO of them: once `clientWidth` already matched the new width, the
  // header row still wore the previous width's padding in all three engines,
  // and still after one frame in WebKit (7 of 30 resizes) — never after two.
  // A time window alone let that stale layout through under load, reported as
  // an overlap the settled header does not have.
  await page.evaluate(
    () =>
      new Promise<void>(done => requestAnimationFrame(() => requestAnimationFrame(() => done())))
  );
  // Then stable means unchanged for 300 ms: the swaps above are asynchronous.
  let previous = await signature();
  let unchanged = 0;
  for (let attempt = 0; attempt < 30; attempt++) {
    await page.waitForTimeout(150);
    const current = await signature();
    unchanged = current === previous && current !== '' ? unchanged + 1 : 0;
    if (unchanged >= 2) return;
    previous = current;
  }
}

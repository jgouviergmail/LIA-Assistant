/**
 * The hero avatar picker — a contract written entirely in CSS.
 *
 * The whole hero image has always been a click target that flips LIA's avatar.
 * It is invisible, so the change reads as accidental. The picker makes the
 * choice visible without removing that target, and everything that makes it
 * work is `opacity` driven by `group-hover` / `group-focus-within` plus a
 * responsive touch size. jsdom computes none of that: a unit test sees the
 * class strings and can only assert that they are spelled the way the test
 * expects, which proves nothing about what a reader sees.
 *
 * Four properties, each of which has a plausible way to break silently:
 *
 * - discreet at rest on a pointer device, revealed on hover;
 * - **revealed by the keyboard too** — a picker that only answered the mouse
 *   would be unreachable for anyone tabbing, since the thing that reveals it
 *   is the focus that has to land inside it;
 * - always visible and 44 px on touch, where there is no hover at all;
 * - a sibling of the full-surface button, not a descendant: pressing a
 *   portrait must select it, never fall through to the blind flip underneath.
 */
import type { Locator } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

const GENERATED_AT = '2026-08-03T08:00:00Z';

/** A section that resolved and has nothing to show. */
const empty = {
  status: 'empty',
  data: null,
  generated_at: GENERATED_AT,
  error_code: null,
  error_message: null,
};

/**
 * All NINE sections, because `CardsBundle` declares all nine as required — the
 * backend cannot omit one. A partial bundle is not a lighter fixture, it is an
 * impossible payload: `visibleOrderedSections` keeps every name the
 * preferences do not hide, and `BriefingCard` then reads `section.status` off
 * `undefined` and the error boundary replaces the entire dashboard — hero
 * included. Landmark-only assertions survive that; anything about the page
 * itself does not.
 */
const dashboardData: MockRoute[] = [
  {
    url: '**/api/v1/briefing/cards',
    json: {
      cards: {
        weather: empty,
        agenda: empty,
        mails: empty,
        birthdays: empty,
        health: empty,
        tasks: empty,
        documents: empty,
        reminders: empty,
        for_you: empty,
      },
    },
  },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: { text: 'Welcome back', generated_at: null, usage: null }, synthesis: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

/** Computed opacity of an element, as a number. */
async function opacityOf(locator: Locator): Promise<number> {
  return Number(await locator.evaluate(el => getComputedStyle(el).opacity));
}

test.describe('hero avatar picker', () => {
  test('is discreet at rest and revealed by hover on a pointer device', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(dashboardData);
    await page.goto('/en/dashboard');

    const group = page.getByRole('group', { name: "Choose LIA's avatar" });
    await expect(group).toBeAttached();

    // At rest: present in the tree (so the keyboard can still reach it) but
    // faded out. Playwright's own `toBeVisible` treats opacity 0 as visible,
    // which is exactly why this reads the computed value instead.
    expect(await opacityOf(group)).toBeLessThan(0.05);

    // The full-surface toggle carries the `group` the reveal keys off; hovering
    // the hero is what a reader actually does before reaching for the picker.
    await page.getByRole('button', { name: "Switch LIA's avatar" }).hover();
    await expect
      .poll(async () => await opacityOf(group), { timeout: 3_000 })
      .toBeGreaterThan(0.95);
  });

  test('is revealed by the keyboard, not only by the mouse', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(dashboardData);
    await page.goto('/en/dashboard');

    const group = page.getByRole('group', { name: "Choose LIA's avatar" });
    await expect(group).toBeAttached();
    expect(await opacityOf(group)).toBeLessThan(0.05);

    // Focus lands inside the group WITHOUT any pointer involved. If the reveal
    // were hover-only, this control would be permanently invisible to anyone
    // navigating by keyboard while still occupying a tab stop — the worst of
    // both worlds.
    await page.getByRole('button', { name: 'Feminine portrait' }).focus();

    await expect
      .poll(async () => await opacityOf(group), { timeout: 3_000 })
      .toBeGreaterThan(0.95);
  });

  test('is always visible and a full 44 px target on touch', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // 390 x 844 — iPhone-class viewport, below the `sm` breakpoint.
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(dashboardData);
    await page.goto('/en/dashboard');

    const group = page.getByRole('group', { name: "Choose LIA's avatar" });
    await expect(group).toBeAttached();

    // There is no hover on a finger: anything revealed by it would never be
    // revealed at all.
    expect(await opacityOf(group)).toBeGreaterThan(0.95);

    for (const name of ['Feminine portrait', 'Masculine portrait']) {
      const box = await page.getByRole('button', { name }).boundingBox();
      expect(box, `${name} must be laid out`).not.toBeNull();
      expect(box!.width, `${name} width`).toBeGreaterThanOrEqual(44);
      expect(box!.height, `${name} height`).toBeGreaterThanOrEqual(44);
    }
  });

  test('selects the pressed portrait rather than flipping blindly', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(dashboardData);
    await page.goto('/en/dashboard');

    const feminine = page.getByRole('button', { name: 'Feminine portrait' });
    const masculine = page.getByRole('button', { name: 'Masculine portrait' });
    await expect(feminine).toBeVisible();

    // Establish a known state first. Starting from whatever the default
    // happens to be would make the first assertion pass for free on half the
    // possible defaults, and silently stop testing anything if that default
    // ever changed.
    await feminine.click();
    await expect(feminine).toHaveAttribute('aria-pressed', 'true');
    await expect(masculine).toHaveAttribute('aria-pressed', 'false');

    await masculine.click();
    await expect(masculine).toHaveAttribute('aria-pressed', 'true');
    await expect(feminine).toHaveAttribute('aria-pressed', 'false');

    // Pressing the one already active is a NO-OP, which is the whole point of
    // a selection: the full-surface button underneath would have flipped back,
    // and this same press would read as "nothing I do sticks".
    await masculine.click();
    await expect(masculine).toHaveAttribute('aria-pressed', 'true');
    await expect(feminine).toHaveAttribute('aria-pressed', 'false');
  });
});

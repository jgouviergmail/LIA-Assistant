/** Current native animated avatar plus a smaller opposite variant: real geometry,
 * pointer/touch, keyboard/focus and cookie persistence in all browser engines. */
import type { Page } from '@playwright/test';

import { test, expect, briefingWindowsMock, waitForHydration, type MockRoute } from '../fixtures';

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
 * Every section, because `CardsBundle` declares each as required — the
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
      windows: briefingWindowsMock,
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
        workboard: empty,
      },
    },
  },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: { text: 'Welcome back', generated_at: null, usage: null }, synthesis: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

/** One visible opposite portrait, below the selected native animated avatar. */
const pair = (page: Page) => page.getByRole('group', { name: "Choose LIA's avatar", exact: true });
async function femaleStart(page: Page) {
  await page
    .context()
    .addCookies([{ name: 'lia_gender', value: 'female', domain: 'localhost', path: '/' }]);
  await page.goto('/en/dashboard');
  await waitForHydration(page, 'main');
  await expect(
    pair(page).getByRole('img', { name: 'Feminine portrait', exact: true })
  ).toBeVisible();
  await expect(pair(page).locator('[data-companion-portrait]')).toHaveCount(2);
}

test.describe('hero animated avatar pair', () => {
  test('shows the current native skin above a smaller opposite portrait, centered with the greeting', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(dashboardData);
    await femaleStart(page);
    const group = pair(page);
    await expect(group.getByRole('button')).toHaveCount(1);
    const main = group.getByRole('img', { name: 'Feminine portrait', exact: true });
    const alternate = group.getByRole('button', { name: 'Masculine portrait', exact: true });
    await expect(alternate).toBeVisible();
    const big = main.locator('[data-companion-portrait]');
    const small = alternate.locator('[data-companion-portrait]');
    await expect(big).toHaveAttribute('data-portrait-variant', 'female');
    await expect(small).toHaveAttribute('data-portrait-variant', 'male');
    expect(await big.getAttribute('data-companion-portrait')).toBe(
      await small.getAttribute('data-companion-portrait')
    );
    const [a, b, g, text] = await Promise.all([
      big.boundingBox(),
      small.boundingBox(),
      group.boundingBox(),
      page.getByText('Welcome back', { exact: true }).boundingBox(),
    ]);
    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
    expect(g).not.toBeNull();
    expect(text).not.toBeNull();
    expect(a!.width).toBeGreaterThan(b!.width * 1.8);
    expect(b!.y).toBeGreaterThanOrEqual(a!.y + a!.height);
    expect(Math.abs(g!.y + g!.height / 2 - text!.y - text!.height / 2)).toBeLessThanOrEqual(3);
  });

  test('exchanges portraits both ways and persists the selected preference across reload', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(dashboardData);
    await femaleStart(page);
    const group = pair(page);
    const trigger = group.getByRole('button');
    await trigger.click();
    await expect(group.getByRole('img', { name: 'Masculine portrait', exact: true })).toBeVisible();
    await expect(trigger).toHaveAccessibleName('Feminine portrait');
    await expect(trigger).toBeFocused();
    expect((await page.context().cookies()).find(c => c.name === 'lia_gender')?.value).toBe('male');
    await page.reload();
    await waitForHydration(page, 'main');
    await expect(group.getByRole('img', { name: 'Masculine portrait', exact: true })).toBeVisible();
    await trigger.click();
    await expect(group.getByRole('img', { name: 'Feminine portrait', exact: true })).toBeVisible();
    await expect(trigger).toHaveAccessibleName('Masculine portrait');
    expect((await page.context().cookies()).find(c => c.name === 'lia_gender')?.value).toBe(
      'female'
    );
  });

  test('is reached directly by keyboard and keeps focus when the images exchange', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(dashboardData);
    await femaleStart(page);
    const trigger = pair(page).getByRole('button');
    await page.getByRole('button', { name: 'Sign out', exact: true }).focus();
    await page.keyboard.press('Tab');
    await expect(trigger).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(trigger).toHaveAccessibleName('Feminine portrait');
    await expect(trigger).toBeFocused();
    await page.keyboard.press('Space');
    await expect(trigger).toHaveAccessibleName('Masculine portrait');
    await expect(trigger).toBeFocused();
  });

  test('keeps a 44px touch target and never flips when the main portrait is pressed', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(dashboardData);
    await femaleStart(page);
    const group = pair(page);
    const trigger = group.getByRole('button', { name: 'Masculine portrait', exact: true });
    const target = await trigger.boundingBox();
    expect(target).not.toBeNull();
    expect(target!.width).toBeGreaterThanOrEqual(44);
    expect(target!.height).toBeGreaterThanOrEqual(44);
    await group.getByRole('img', { name: 'Feminine portrait', exact: true }).click();
    await expect(trigger).toBeVisible();
    expect((await page.context().cookies()).find(c => c.name === 'lia_gender')?.value).toBe(
      'female'
    );
    await trigger.click();
    await expect(group.getByRole('img', { name: 'Masculine portrait', exact: true })).toBeVisible();
  });
});

/**
 * A control that saves its own change keeps the keyboard: busy, never disabled.
 *
 * Measured 2026-11-13 on Settings › Images: the list and the switch were `disabled` while
 * their change was being saved, so the browser refused the focus to them and a keyboard
 * user landed on `<body>`. `Select`'s and `Switch`'s `busy` keep the control focusable,
 * announced as busy and deaf to a second change until the save answers. jsdom does not
 * apply the browser's focus rules, so these journeys are the proof.
 */
import { test, expect, waitForHydration, waitForMockGate } from '../fixtures';
import { surfaceRoutes } from '../fixtures/settings-surfaces';

test('a list saving its own choice keeps the keyboard focus', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate();
  let answer!: () => void;
  const saved = new Promise<void>(resolve => (answer = resolve));
  await mockApi([
    ...surfaceRoutes,
    {
      url: `**/api/v1/users/${user.id}`,
      method: 'PATCH',
      handler: async (route, signal) => {
        if (!(await waitForMockGate(saved, signal))) return;
        await route.fulfill({ json: { ...user, image_generation_output_format: 'jpeg' } });
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=image-generation');
  await waitForHydration(page, 'main');

  const trigger = page.getByRole('combobox', { name: 'Output format' });
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('option', { name: 'PNG', exact: true })).toBeFocused();
  // Radix moves the focus of an arrow key on the next tick: wait for it, as a hand would.
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('option', { name: 'JPEG', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');

  // The save is held: the list keeps the focus, says it is busy and does not reopen.
  await expect(trigger).toHaveAttribute('aria-busy', 'true');
  await expect(trigger).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('listbox')).toHaveCount(0);

  answer();
  await expect(trigger).not.toHaveAttribute('aria-busy');
  await expect(trigger).toBeFocused();
});

test('a switch saving its own change keeps the keyboard focus', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate();
  let answer!: () => void;
  const saved = new Promise<void>(resolve => (answer = resolve));
  let patches = 0;
  await mockApi([
    ...surfaceRoutes,
    {
      url: `**/api/v1/users/${user.id}`,
      method: 'PATCH',
      handler: async (route, signal) => {
        patches += 1;
        if (!(await waitForMockGate(saved, signal))) return;
        await route.fulfill({ json: { ...user, image_generation_enabled: true } });
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=image-generation');
  await waitForHydration(page, 'main');

  const toggle = page.getByRole('switch', { name: 'Enable image generation' });
  await toggle.focus();
  await page.keyboard.press('Space');

  // The save is held: the switch keeps the focus, says it is busy and takes no second toggle.
  await expect(toggle).toHaveAttribute('aria-busy', 'true');
  await expect(toggle).toBeFocused();
  await page.keyboard.press('Space');
  expect(patches).toBe(1);

  answer();
  await expect(toggle).not.toHaveAttribute('aria-busy');
  await expect(toggle).toBeFocused();
});

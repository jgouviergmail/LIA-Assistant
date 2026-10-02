/**
 * Hands-free badge — turned off, a click on it turns it back on.
 *
 * The badge used to toast « Hands-free mode off » on a long press. The toaster
 * stacks at the top centre, right over the chat header's centre group, so the
 * toast covered the badge and swallowed the very click meant to turn the mode
 * back on (measured 2026-10-01). The transitions are now announced through a
 * polite status beside the badge; this journey holds the click path in a real
 * browser, which the unit tests (a mocked hook, no layout) cannot see.
 */
import { test, expect, loadedChatRoutes } from '../fixtures';

test.use({
  launchOptions: {
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
});

// The fake microphone is a Chromium launch flag: WebKit refuses to start with it,
// and Playwright grants Firefox no microphone permission (both measured in the
// browser matrix).
test.skip(({ browserName }) => browserName !== 'chromium', 'the fake microphone is Chromium-only');

test('a click turns hands-free mode back on right after a long press turned it off', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ language: 'fr' });
  await mockApi(loadedChatRoutes());
  await page.route('**/api/v1/auth/me/voice-mode-preference', route =>
    route.fulfill({
      json: { voice_mode_enabled: true, voice_stt_mode: 'local', stt_remote_available: false },
    })
  );
  await page.goto('/fr/dashboard/chat');
  await page.locator('textarea').first().waitFor({ state: 'visible' });

  const badge = page.locator('button[aria-pressed]').first();
  await expect(badge).toHaveAttribute('aria-pressed', 'false');

  await badge.click();
  await expect(badge).toHaveAttribute('aria-pressed', 'true');

  // Long press: the mode goes off.
  const box = await badge.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(800);
  await page.mouse.up();
  await expect(badge).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('status').filter({ hasText: 'désactivé' })).toBeAttached();

  // Nothing covers the badge: the very next click turns the mode back on.
  await badge.click({ timeout: 2_000 });
  await expect(badge).toHaveAttribute('aria-pressed', 'true');
});

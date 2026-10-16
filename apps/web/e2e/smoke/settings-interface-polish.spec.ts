/** User-facing polish, served by Docker with every API call intercepted. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect, idleNotificationStream, type MockRoute } from '../fixtures';

test.use({ navigationTimeout: 180_000 });

const dictionary: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/en/translation.json'), 'utf8')
);
function label(key: string): string {
  let value: unknown = dictionary;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing label ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing label ${key}`);
  return value;
}
const baseRoutes: MockRoute[] = [
  { url: '**/api/runtime-ui', json: { avatarStyleRolloutId: null } },
  { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  {
    url: '**/api/v1/system-settings/debug-panel-status',
    json: { enabled: false, user_access_available: false },
  },
  { url: '**/api/v1/habits/presence', method: 'POST', status: 204 },
  idleNotificationStream,
  { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
  { url: '**/api/v1/usage/**', json: {} },
];

test('four display modes include absolute black without a separate switch', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ theme: 'light', voice_enabled: false });
  const patches: unknown[] = [];
  await mockApi([
    ...baseRoutes,
    {
      url: `**/api/v1/users/${user.id}`,
      method: 'PATCH',
      handler: async route => {
        const body = route.request().postDataJSON();
        patches.push(body);
        Object.assign(user, body);
        await route.fulfill({ json: user });
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=theme');
  const section = page.locator('#settings-section-theme');
  await expect(section).toBeVisible({ timeout: 60_000 });
  await expect(section.getByRole('radio')).toHaveCount(4);
  await expect(section.getByRole('switch')).toHaveCount(0);
  for (const name of ['light', 'dark', 'oled', 'system'])
    await expect(
      section.getByRole('radio', { name: label(`settings.theme.${name}`), exact: true })
    ).toHaveCount(1);
  const black = section.getByRole('radio', { name: label('settings.theme.oled'), exact: true });
  await section.getByText(label('settings.theme.oled'), { exact: true }).click();
  await expect(black).toBeChecked();
  await expect(page.locator('html')).toHaveAttribute('data-oled', '');
  await expect.poll(() => patches).toContainEqual({ theme: 'oled' });
  for (const mode of ['light', 'dark', 'oled']) {
    const radio = section.getByRole('radio', {
      name: label(`settings.theme.${mode}`),
      exact: true,
    });
    await section.getByText(label(`settings.theme.${mode}`), { exact: true }).click();
    await expect(radio).toBeChecked();
    await expect
      .poll(
        () =>
          section.evaluate(element => {
            const nested = element.querySelector(
              'label:has(input[name="display-mode"]:not(:checked))'
            );
            if (!nested) throw new Error('Expected an unselected nested mode');
            const canvas = document.createElement('canvas');
            canvas.width = canvas.height = 1;
            const context = canvas.getContext('2d');
            if (!context) throw new Error('Expected canvas color conversion');
            function luminance(color: string) {
              context!.clearRect(0, 0, 1, 1);
              context!.fillStyle = color;
              context!.fillRect(0, 0, 1, 1);
              const rgba = context!.getImageData(0, 0, 1, 1).data;
              if (rgba[3] !== 255) throw new Error('Expected opaque settings surfaces');
              const linear = Array.from(rgba)
                .slice(0, 3)
                .map(value => {
                  const channel = value / 255;
                  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
                });
              return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
            }
            return (
              luminance(getComputedStyle(element).backgroundColor) >
              luminance(getComputedStyle(nested).backgroundColor)
            );
          }),
        `${mode}: the primary card is lighter than its unselected nested mode`
      )
      .toBe(true);
  }
});

test('font size keeps its named keyboard slider without a visible value or default badge', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ font_size: 16, voice_enabled: false });
  await mockApi(baseRoutes);
  await page.goto('/en/dashboard/settings?section=font-size');
  const section = page.locator('#settings-section-font-size');
  const slider = section.getByRole('slider', { name: label('settings.font_size.slider_label') });
  await expect(slider).toBeVisible();
  await expect(slider).toHaveAttribute('aria-valuenow', '16');
  await expect(slider).toHaveAttribute('aria-valuetext', /16/);
  await expect(section.getByText(/\b16\s*px\b/)).toHaveCount(0);
  await expect(
    section.getByText(label('settings.font_size.default_badge'), { exact: true })
  ).toHaveCount(0);
});

test('the routines week stays closed on arrival', async ({ page, authenticate, mockApi }) => {
  await authenticate({ voice_enabled: false });
  const routine = {
    id: '00000000-0000-4000-8000-00000000c322',
    title: 'Morning check',
    action_prompt: 'Check the day',
    recurrence: null,
    user_timezone: 'Europe/Paris',
    trigger_kind: 'condition',
    condition_config: { type: 'task_overdue', until: '2099-12-31' },
    requires_approval: false,
    execution_mode: 'react',
    next_trigger_at: '2099-12-31T10:00:00Z',
    is_enabled: true,
    status: 'active',
    execution_count: 0,
    consecutive_failures: 0,
    last_executed_at: null,
    last_error: null,
    schedule_display: 'Every ten minutes',
    times_of_day: [],
    runs_per_day: 0,
    next_occurrences: [],
    week_slots: [],
    check_interval_minutes: 10,
    last_checked_at: null,
    last_check_error: null,
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T10:00:00Z',
  };
  await mockApi([
    ...baseRoutes,
    {
      url: '**/api/v1/scheduled-actions',
      method: 'GET',
      json: { scheduled_actions: [routine], total: 1 },
    },
    {
      url: '**/api/v1/scheduled-actions/week**',
      json: { actions: [], generated_at: '2026-10-16T10:00:00Z' },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=scheduled-actions');
  const section = page.locator('#settings-section-scheduled-actions');
  await expect(section.getByText('Morning check', { exact: true })).toBeVisible();
  const summary = section
    .locator('summary')
    .filter({ hasText: label('scheduled_actions.timeline.title') });
  await expect(summary).toBeVisible();
  await expect(summary.locator('..')).not.toHaveAttribute('open', '');
  await expect(section.getByRole('table')).toHaveCount(0);
});

test('failed plugin loading offers Retry before showing a confirmed empty list', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ voice_enabled: false });
  let calls = 0;
  await mockApi([
    ...baseRoutes,
    {
      url: '**/api/v1/plugins',
      method: 'GET',
      handler: async route => {
        calls += 1;
        await route.fulfill(
          calls === 1
            ? { status: 503, json: { detail: 'fixture unavailable' } }
            : { json: { plugins: [], total: 0 } }
        );
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=plugins');
  const section = page.locator('#settings-section-plugins');
  await expect(section.getByRole('alert')).toContainText(label('settings.plugins.load_error'));
  await expect(section.getByText(label('settings.plugins.empty'), { exact: true })).toHaveCount(0);
  await section.getByRole('button', { name: label('common.retry'), exact: true }).click();
  await expect(section.getByText(label('settings.plugins.empty'), { exact: true })).toBeVisible();
  expect(calls).toBe(2);
});

test('the initially open psyche point reads once per opening', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ voice_enabled: false });
  let summaries = 0;
  await mockApi([
    ...baseRoutes,
    {
      url: '**/api/v1/psyche/settings',
      json: {
        psyche_enabled: true,
        psyche_display_avatar: true,
        psyche_sensitivity: 50,
        psyche_stability: 65,
      },
    },
    { url: '**/api/v1/psyche/history**', json: [] },
    {
      url: '**/api/v1/psyche/summary',
      handler: async route => {
        summaries += 1;
        await route.fulfill({ json: { summary: 'Fixture point about LIA' } });
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=psyche');
  const section = page.locator('#settings-section-psyche');
  const point = section.locator('summary').filter({ hasText: label('psyche.presentation.point') });
  await expect(point).toBeVisible();
  await expect(section.getByText('Fixture point about LIA', { exact: true })).toBeVisible();
  await expect(point.locator('..')).toHaveAttribute('open', '');
  expect(summaries).toBe(1);
  await point.click();
  await expect(point.locator('..')).not.toHaveAttribute('open', '');
  await point.click();
  await expect(section.getByText('Fixture point about LIA', { exact: true })).toBeVisible();
  expect(summaries, 'one read belongs to each opening of the point').toBe(2);
});

test('mobile search remains reachable with a custom BIP position and restores the settings rail', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({
        state: { visible: true, size: 'xl', style: 'billes', position: { xPct: 5, yPct: 16 } },
        version: 0,
      })
    )
  );
  await authenticate({ voice_enabled: false, theme: 'oled', font_size: 20 });
  await mockApi(baseRoutes);
  await page.goto('/en/dashboard/settings');
  const search = page.getByRole('combobox', { name: label('settings.search.label') });
  await expect(page.locator('.lia-eyes-widget')).toBeVisible({ timeout: 60_000 });
  await expect(search).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('.lia-eyes-widget')).toHaveAttribute('data-compact', 'true');
  await expect
    .poll(() =>
      page.evaluate(() => {
        const widget = document.querySelector('.lia-eyes-widget')?.getBoundingClientRect();
        const title = document.querySelector('main h1')?.getBoundingClientRect();
        return (
          !!widget &&
          !!title &&
          (widget.right <= title.left ||
            widget.left >= title.right ||
            widget.bottom <= title.top ||
            widget.top >= title.bottom)
        );
      })
    )
    .toBe(true);

  await expect
    .poll(() =>
      search.evaluate(element => {
        const bounds = element.getBoundingClientRect();
        return [0.1, 0.5, 0.9].every(fraction => {
          const hit = document.elementFromPoint(
            bounds.left + bounds.width * fraction,
            bounds.top + bounds.height / 2
          );
          return hit === element || element.contains(hit);
        });
      })
    )
    .toBe(true);
  await page.screenshot({
    path: testInfo.outputPath('mobile-search-bip-black-before.png'),
    fullPage: true,
  });
  await search.click();
  await search.fill('font');
  await expect(page.getByRole('listbox')).toBeVisible();
  await page.getByRole('option').first().click();
  await expect(page.locator('[id^="settings-section-"]').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true
  );
  await page.getByRole('button', { name: label('settings.shell.back'), exact: true }).click();
  await expect(search).toBeVisible();
  await expect(search).toBeFocused();
  await page.screenshot({
    path: testInfo.outputPath('mobile-search-bip-black-return.png'),
    fullPage: true,
  });
  // Exercise LIA's actual text scaling contract and a real resize notification.
  await page.evaluate(() => document.documentElement.style.setProperty('--lia-text-scale', '2'));
  await page.setViewportSize({ width: 361, height: 801 });
  await page.setViewportSize({ width: 360, height: 800 });
  await expect(search).toBeVisible();
  await expect
    .poll(() =>
      search.evaluate(element => {
        const bounds = element.getBoundingClientRect();
        return [0.1, 0.5, 0.9].every(fraction => {
          const hit = document.elementFromPoint(
            bounds.left + bounds.width * fraction,
            bounds.top + bounds.height / 2
          );
          return hit === element || element.contains(hit);
        });
      })
    )
    .toBe(true);
  await search.click();
  await search.fill('theme');
  await expect(page.getByRole('listbox')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true
  );
  await expect(page.locator('.lia-eyes-widget')).toHaveAttribute('data-compact', 'true');
  await expect
    .poll(() =>
      page.evaluate(() => {
        const widget = document.querySelector('.lia-eyes-widget')?.getBoundingClientRect();
        const title = document.querySelector('main h1')?.getBoundingClientRect();
        return (
          !!widget &&
          !!title &&
          (widget.right <= title.left ||
            widget.left >= title.right ||
            widget.bottom <= title.top ||
            widget.top >= title.bottom)
        );
      })
    )
    .toBe(true);

  await page.screenshot({
    path: testInfo.outputPath('mobile-search-bip-black-text-200-percent.png'),
    fullPage: true,
  });
});

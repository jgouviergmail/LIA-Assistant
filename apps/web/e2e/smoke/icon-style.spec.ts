/** Account icon selection through real navigation, settings and archived cards. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator } from '@playwright/test';
import {
  test,
  expect,
  idleNotificationStream,
  loadedChatRoutes,
  type MockRoute,
  type TestUser,
} from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

type IconStyle = TestUser['icon_style'];
const dictionary: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/en/translation.json'), 'utf8')
);
const frenchDictionary: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
function label(key: string, source: unknown = dictionary): string {
  let value: unknown = source;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing label ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing label ${key}`);
  return value;
}

function iconChoice(body: unknown): IconStyle {
  if (!body || typeof body !== 'object') throw new Error('Expected icon preference PATCH');
  const choice = (body as Record<string, unknown>).icon_style;
  if (choice !== 'lucide' && choice !== 'fluent' && choice !== 'flex') {
    throw new Error('Expected a supported icon style');
  }
  expect(Object.keys(body)).toEqual(['icon_style']);
  return choice;
}

/** Geometry alone: paint, generated IDs and wrapper groups cannot change a thumb's meaning. */
async function iconGeometry(icon: Locator): Promise<string[]> {
  return icon.evaluate(svg =>
    Array.from(svg.querySelectorAll('path,rect,circle,ellipse,line,polyline,polygon'), node => {
      const geometry = [
        'd',
        'x',
        'y',
        'width',
        'height',
        'rx',
        'ry',
        'cx',
        'cy',
        'r',
        'x1',
        'x2',
        'y1',
        'y2',
        'points',
        'transform',
      ];
      return JSON.stringify([
        node.tagName.toLowerCase(),
        geometry.flatMap(name => {
          const value = node.getAttribute(name);
          return value === null ? [] : [[name, value.replace(/\s+/g, '')]];
        }),
      ]);
    })
  );
}

async function expectControlIcon(button: Locator, name: string, style: IconStyle) {
  await expect(button).toBeVisible();
  await expect(button).toHaveAccessibleName(/\S+/);
  const icon = button.locator(`svg[data-icon-name="${name}"]`);
  await expect(icon).toBeVisible();
  await expect(icon).toHaveAttribute('data-icon-style', style);
  expect((await icon.boundingBox())?.width).toBeGreaterThanOrEqual(13);
  expect((await iconGeometry(icon)).length).toBeGreaterThan(0);
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

const savedCard = {
  id: '00000000-0000-4000-8000-000000000101',
  role: 'assistant',
  content:
    '<div class="lia-card"><p><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">mail</span></span>Saved icon comparison</p>' +
    ['star', 'star_half', 'star_outline', 'favorite', 'favorite_border']
      .map(name => `<span class="material-symbols-outlined" title="rating-${name}">${name}</span>`)
      .join('') +
    '<span class="material-symbols-outlined" title="historical-icon">account_balance</span>' +
    '</div>',
  created_at: '2026-11-08T10:00:00Z',
};

for (const theme of ['light', 'dark'] as const) {
  test(`all three styles reach navigation, appearance and saved cards in ${theme} mode`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    // The cost toggle is intentionally offered at 2xl, alongside all feature controls.
    await page.setViewportSize({ width: 1600, height: 1000 });
    const user = await authenticate({ theme, icon_style: 'fluent', execution_mode: 'react' });
    const patches: IconStyle[] = [];
    const feedback: unknown[] = [];
    let lucideThumbs: { up: string[]; down: string[] } | undefined;
    await mockApi([
      ...baseRoutes,
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/config',
        json: {
          ...appConfig,
          features: {
            ...appConfig.features,
            meetings_enabled: true,
            radio_enabled: true,
            bookmarks_enabled: true,
            peers_enabled: true,
            email_share_enabled: true,
          },
        },
      },
      { url: '**/api/v1/bookmarks/state', json: { message_ids: {} } },
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [savedCard],
          conversation_id: '00000000-0000-4000-8000-000000000100',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
      {
        url: `**/api/v1/users/${user.id}`,
        method: 'PATCH',
        handler: async route => {
          const body: unknown = route.request().postDataJSON();
          user.icon_style = iconChoice(body);
          patches.push(user.icon_style);
          await route.fulfill({ json: user });
        },
      },
      {
        url: `**/api/v1/conversations/me/messages/${savedCard.id}/feedback`,
        method: 'POST',
        handler: async route => {
          const body: unknown = route.request().postDataJSON();
          feedback.push(body);
          await route.fulfill({ json: { message: 'Feedback saved' } });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=theme');
    const section = page.locator('#settings-section-theme');
    const styles = section.getByRole('group', { name: label('settings.theme.icons.title') });
    await expect(styles).toBeVisible();
    if (theme === 'dark') await expect(page.locator('html')).toHaveClass(/\bdark\b/);
    else await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);
    await expect(styles.getByRole('radio')).toHaveCount(3);
    await expect(styles.getByRole('radio', { name: 'Fluent Color', exact: true })).toBeChecked();

    for (const style of ['lucide', 'fluent', 'flex'] as const) {
      // A real native radio group owns arrow navigation and preserves focus
      // while the serialized account PATCH is in flight. Use adjacent arrows:
      // native WebKit stops at a group's boundary without wrapping.
      await styles.locator('input:checked').focus();
      await page.keyboard.press(style === 'lucide' ? 'ArrowLeft' : 'ArrowRight');
      const selected = styles.getByRole('radio', {
        name: label(`settings.theme.icons.${style}`),
        exact: true,
      });
      await expect(selected).toBeChecked();
      await expect(selected).toBeFocused();
      await expect.poll(() => patches.at(-1)).toBe(style);
      await expect(styles).toHaveAttribute('aria-busy', 'false');
      await expect(page.locator('nav a[href="/en/dashboard/chat"] svg').first()).toHaveAttribute(
        'data-icon-style',
        style
      );
      await expect(
        selected.locator('..').locator('svg[data-icon-name="Calendar"]')
      ).toHaveAttribute('data-icon-style', style);
      await awaitStyledPage(page, `${theme} ${style} appearance`);
      await testInfo.attach(`${theme}-${style}-appearance`, {
        body: await page.screenshot({
          path: testInfo.outputPath(`${theme}-${style}-appearance.png`),
        }),
        contentType: 'image/png',
      });

      // A full navigation reads /auth/me again: the chosen style must come
      // from the saved account, not a surviving local component override.
      await page.goto('/en/dashboard/chat');
      await expect(page.getByText('Saved icon comparison', { exact: true })).toBeVisible();
      await expect(
        page.locator('.lia-card .lia-symbol-icon > svg[data-icon-name="Mail"]')
      ).toHaveAttribute('data-icon-style', style);
      const header = page.locator('header');
      for (const [key, name] of [
        ['executionMode.toggle.enable_pipeline', 'Zap'],
        ['meetings.header.record', 'Disc'],
        ['radio.header.start', 'Radio'],
        ['voice.toggle.enable', 'VolumeX'],
        ['tokens_display.toggle.disable', 'CircleDollarSign'],
        [
          theme === 'light' ? 'theme.to_dark' : 'theme.to_oled',
          theme === 'light' ? 'Moon' : 'Eclipse',
        ],
      ]) {
        await expectControlIcon(
          header.getByRole('button', { name: label(key), exact: true }),
          name,
          style
        );
      }
      const bubble = page
        .locator('.message-bubble-assistant')
        .filter({ hasText: 'Saved icon comparison' });
      for (const name of ['star', 'star_half', 'star_outline', 'favorite', 'favorite_border']) {
        const svg = bubble.getByTitle(`rating-${name}`, { exact: true }).locator('svg');
        const filled = name === 'star' || name === 'star_half' || name === 'favorite';
        await expect(svg).toHaveAttribute('fill', filled ? 'currentColor' : 'none');
        const paint = await svg.evaluate(element => {
          const body = element.querySelector('[fill="inherit"]') ?? element.querySelector('path');
          if (!body) throw new Error('The state-bearing icon needs its real semantic shape');
          return { root: getComputedStyle(element).fill, body: getComputedStyle(body).fill };
        });
        expect(paint.body).toBe(paint.root);
        if (!filled) expect(paint.body).toBe('none');
        else expect(paint.body).not.toBe('none');
      }
      const historical = bubble.getByTitle('historical-icon', { exact: true });
      await expect(historical).toHaveText('account_balance');
      await expect(historical.locator('svg')).toHaveCount(0);
      await expect(historical).toHaveAttribute('data-icon-style', style);
      const historicalPaint = await historical.evaluate(element => ({
        fill: getComputedStyle(element).webkitTextFillColor,
        background: getComputedStyle(element).backgroundImage,
      }));
      if (style === 'lucide') {
        expect(historicalPaint.fill).not.toBe('rgba(0, 0, 0, 0)');
        expect(historicalPaint.background).toBe('none');
      } else {
        expect(historicalPaint.fill).toBe('rgba(0, 0, 0, 0)');
        expect(historicalPaint.background).toMatch(/^linear-gradient\(/);
      }
      for (const [key, name] of [
        ['chat.message.copy', 'Copy'],
        ['chat.message.bookmark', 'Bookmark'],
        ['chat.message.share', 'Share2'],
        ['chat.message.download_md', 'Download'],
        ['email_share.button', 'Mail'],
        ['chat.feedback.up', 'ThumbsUp'],
        ['chat.feedback.down', 'ThumbsDown'],
      ]) {
        await expectControlIcon(
          bubble.getByRole('button', { name: label(key), exact: true }),
          name,
          style
        );
      }
      const up = page.getByRole('button', { name: label('chat.feedback.up'), exact: true });
      const down = page.getByRole('button', { name: label('chat.feedback.down'), exact: true });
      const thumbs = {
        up: await iconGeometry(up.locator('svg')),
        down: await iconGeometry(down.locator('svg')),
      };
      expect(thumbs.up).not.toEqual(thumbs.down);
      if (style === 'lucide') lucideThumbs = thumbs;
      else if (style === 'fluent') {
        expect(
          lucideThumbs,
          'Lucide establishes the real up/down drawing before Fluent'
        ).toBeDefined();
        if (!lucideThumbs) throw new Error('The canonical Lucide thumbs were not rendered');
        // The multicolor complement retains every primitive of the actual
        // thumb silhouette. Decorative paint may add paths, never replace it
        // with a badge or another positive/negative symbol.
        for (const direction of ['up', 'down'] as const) {
          for (const primitive of lucideThumbs[direction]) {
            expect(thumbs[direction]).toContain(primitive);
          }
        }
      } else {
        expect(thumbs.up).not.toEqual(lucideThumbs?.up);
        expect(thumbs.down).not.toEqual(lucideThumbs?.down);
      }
      await expect(up).toHaveAttribute('aria-pressed', 'false');
      await expect(down).toBeEnabled();
      await down.focus();
      await expect(down).toBeFocused();
      await down.press('Enter');
      await expect(down).toHaveAttribute('aria-pressed', 'true');
      await expect(up).toHaveAttribute('aria-pressed', 'false');
      await expect.poll(() => feedback.at(-1)).toEqual({ verdict: 'thumbs_down' });
      await expect(up).toBeEnabled();
      await up.focus();
      await expect(up).toBeFocused();
      await up.press('Enter');
      await expect(up).toHaveAttribute('aria-pressed', 'true');
      await expect(down).toHaveAttribute('aria-pressed', 'false');
      await expect.poll(() => feedback.at(-1)).toEqual({ verdict: 'thumbs_up' });
      // The selected control remains distinguishable even when the icon's
      // intrinsic colours cannot inherit a selected text tint.
      const selectedBorder = await up.evaluate(button => getComputedStyle(button).borderColor);
      const unselectedBorder = await down.evaluate(button => getComputedStyle(button).borderColor);
      expect(selectedBorder).not.toBe(unselectedBorder);
      await testInfo.attach(`${theme}-${style}-card`, {
        body: await page.screenshot({ path: testInfo.outputPath(`${theme}-${style}-card.png`) }),
        contentType: 'image/png',
      });
      if (style === 'fluent') {
        await header.screenshot({ path: testInfo.outputPath(`${theme}-fluent-chat-header.png`) });
        await up
          .locator('..')
          .screenshot({ path: testInfo.outputPath(`${theme}-fluent-message-actions.png`) });
      }
      await page.goto('/en/dashboard/settings?section=theme');
      await expect(selected).toBeChecked();
    }
    await page.reload();
    await expect(styles.getByRole('radio', { name: 'Streamline Flex', exact: true })).toBeChecked();
    expect(patches).toEqual(['lucide', 'fluent', 'flex']);
    expect(feedback).toEqual(
      Array.from({ length: 3 }, () => [{ verdict: 'thumbs_down' }, { verdict: 'thumbs_up' }]).flat()
    );
    await expectNoOverflow(page, `${theme} appearance`);

    // Keep a localized delivery capture on the same verified account/style.
    user.language = 'fr';
    await page.goto('/fr/dashboard/settings?section=theme');
    const frenchStyles = page.getByRole('group', {
      name: label('settings.theme.icons.title', frenchDictionary),
    });
    await expect(
      frenchStyles.getByRole('radio', { name: 'Streamline Flex', exact: true })
    ).toBeChecked();
    await awaitStyledPage(page, `${theme} French appearance`);
    await frenchStyles.scrollIntoViewIfNeeded();
    await testInfo.attach(`${theme}-flex-apparence-fr`, {
      body: await page.screenshot({ path: testInfo.outputPath(`${theme}-flex-apparence-fr.png`) }),
      contentType: 'image/png',
    });
  });
}

test('a failed mobile save keeps the confirmed style and offers a working retry', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 800 });
  const user = await authenticate({ theme: 'dark', icon_style: 'fluent' });
  let attempts = 0;
  await mockApi([
    ...baseRoutes,
    {
      url: `**/api/v1/users/${user.id}`,
      method: 'PATCH',
      handler: async route => {
        const body: unknown = route.request().postDataJSON();
        const choice = iconChoice(body);
        attempts += 1;
        if (attempts === 1) {
          await route.fulfill({ status: 503, json: { detail: 'Fixture temporary refusal' } });
          return;
        }
        user.icon_style = choice;
        await route.fulfill({ json: user });
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=theme');
  const styles = page.getByRole('group', { name: label('settings.theme.icons.title') });
  const fluent = styles.getByRole('radio', { name: 'Fluent Color', exact: true });
  const flex = styles.getByRole('radio', { name: 'Streamline Flex', exact: true });
  await expect(fluent).toBeChecked();
  await fluent.focus();
  await page.keyboard.press('ArrowRight');
  await expect(styles.getByRole('alert')).toContainText(label('settings.theme.icons.save_failed'));
  await expect(fluent).toBeChecked();
  await expect(flex).toBeFocused();
  expect(user.icon_style).toBe('fluent');
  await styles.getByRole('button', { name: label('common.retry'), exact: true }).click();
  await expect(flex).toBeChecked();
  await expect(styles.getByRole('alert')).toHaveCount(0);
  await expect.poll(() => attempts).toBe(2);
  await expect(styles).toHaveAttribute('aria-busy', 'false');
  await page.reload();
  await expect(flex).toBeChecked();
  await awaitStyledPage(page, '320px appearance after retry');
  await expectNoOverflow(page, '320px appearance after retry');
  await styles.scrollIntoViewIfNeeded();
  await testInfo.attach('dark-flex-appearance-320px', {
    body: await page.screenshot({ path: testInfo.outputPath('dark-flex-appearance-320px.png') }),
    contentType: 'image/png',
  });
});

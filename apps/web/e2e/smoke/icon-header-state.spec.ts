/** Selected controls remain readable when their artwork owns its colors. */
import type { Locator } from '@playwright/test';
import { test, expect, loadedChatRoutes } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectDarkIconControlContrast } from '../fixtures/icon-control-contrast';
import { awaitStyledPage } from './overflow-report';

async function buttonPaint(button: Locator) {
  return button.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      border: style.borderTopColor,
      borderWidth: style.borderTopWidth,
      background: style.backgroundColor,
    };
  });
}

test.use({ deviceScaleFactor: 2, reducedMotion: 'reduce' });

for (const sample of [
  { iconStyle: 'fluent', theme: 'light' },
  { iconStyle: 'fluent', theme: 'dark' },
  { iconStyle: 'flex', theme: 'light' },
  { iconStyle: 'flex', theme: 'dark' },
] as const) {
  test(`${sample.iconStyle} ${sample.theme}: cost and radio expose their selected state without motion`, async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }, testInfo) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    const user = await authenticate({
      icon_style: sample.iconStyle,
      theme: sample.theme,
      tokens_display_enabled: false,
    });
    const costChanges: boolean[] = [];
    const starts: unknown[] = [];
    let stops = 0;
    const session = {
      session_id: 'a1b2c3d4-0000-4000-8000-00000000aa01',
      status: 'starting',
      segments: [],
      cost_eur: 0,
      stop_at: null,
      startup_estimate_s: 12,
      end_reason: null,
      mood: 'calm',
    };
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/config',
        json: {
          ...appConfig,
          features: { ...appConfig.features, radio_enabled: true },
          capabilities: { radio: { enabled: true, family: 'media' } },
        },
      },
      {
        url: '**/api/v1/auth/me/tokens-display-preference',
        method: 'PATCH',
        handler: async route => {
          const body: unknown = route.request().postDataJSON();
          if (!body || typeof body !== 'object' || !('tokens_display_enabled' in body)) {
            throw new Error('The cost control must send its account preference');
          }
          const enabled = body.tokens_display_enabled;
          if (typeof enabled !== 'boolean') throw new Error('Expected a boolean cost preference');
          expect(Object.keys(body)).toEqual(['tokens_display_enabled']);
          user.tokens_display_enabled = enabled;
          costChanges.push(enabled);
          await route.fulfill({ json: user });
        },
      },
      {
        url: '**/api/v1/radio/sessions',
        method: 'POST',
        handler: async route => {
          starts.push(route.request().postDataJSON());
          await route.fulfill({ status: 201, json: session });
        },
      },
      {
        url: `**/api/v1/radio/sessions/${session.session_id}/playhead`,
        method: 'POST',
        json: { ...session, status: 'on_air' },
      },
      {
        url: `**/api/v1/radio/sessions/${session.session_id}/stop`,
        method: 'POST',
        handler: async route => {
          stops += 1;
          await route.fulfill({ status: 204, body: '' });
        },
      },
    ]);
    await page.goto('/en/dashboard/chat');
    await awaitStyledPage(page, 'colored header selection');
    const header = page.locator('header');
    const cost = header.getByRole('button', { name: /^(Show|Hide) tokens$/ });
    const radio = header.getByRole('button', { name: /^(Start|Stop) the radio$/ });
    await expect(cost).toHaveAttribute('aria-pressed', 'false');
    await expect(radio).toHaveAttribute('aria-pressed', 'false');
    const costOff = await buttonPaint(cost);
    const radioOff = await buttonPaint(radio);

    await cost.focus();
    await page.keyboard.press('Space');
    await expect(cost).toHaveAccessibleName('Hide tokens');
    await expect(cost).toHaveAttribute('aria-pressed', 'true');
    await expect(cost).toBeEnabled();
    expect(costChanges).toEqual([true]);
    await radio.focus();
    await page.keyboard.press('Space');
    await expect(radio).toHaveAccessibleName('Stop the radio');
    await expect(radio).toHaveAttribute('aria-pressed', 'true');
    expect(starts).toEqual([{}]);
    for (const [button, off, name] of [
      [cost, costOff, 'CircleDollarSign'],
      [radio, radioOff, 'RadioSet'],
    ] as const) {
      const on = await buttonPaint(button);
      expect(on.borderWidth).toBe('1px');
      expect(on.border).not.toBe(off.border);
      expect(on.background).not.toBe(off.background);
      await expect(button.locator(`svg[data-icon-name="${name}"]`)).toHaveAttribute(
        'data-icon-style',
        sample.iconStyle
      );
      if (sample.theme === 'dark') await expectDarkIconControlContrast(button, testInfo);
    }
    await expect(radio.locator('svg')).toHaveCSS('animation-name', 'none');
    if (browserName === 'chromium') {
      const costBox = await cost.boundingBox();
      const radioBox = await radio.boundingBox();
      if (!costBox || !radioBox) throw new Error('Both selected controls must be on screen');
      const left = Math.min(costBox.x, radioBox.x) - 6;
      const top = Math.min(costBox.y, radioBox.y) - 6;
      await page.screenshot({
        path: testInfo.outputPath(`${sample.iconStyle}-${sample.theme}-active-header-controls.png`),
        clip: {
          x: left,
          y: top,
          width: Math.max(costBox.x + costBox.width, radioBox.x + radioBox.width) - left + 6,
          height: Math.max(costBox.y + costBox.height, radioBox.y + radioBox.height) - top + 6,
        },
      });
    }
    await radio.focus();
    await page.keyboard.press('Space');
    await expect(radio).toHaveAttribute('aria-pressed', 'false');
    expect(stops).toBe(1);
    expect(await buttonPaint(radio)).toEqual(radioOff);
    await cost.focus();
    await page.keyboard.press('Space');
    await expect(cost).toHaveAttribute('aria-pressed', 'false');
    await expect(cost).toBeEnabled();
    expect(costChanges).toEqual([true, false]);
    expect(await buttonPaint(cost)).toEqual(costOff);
  });
}

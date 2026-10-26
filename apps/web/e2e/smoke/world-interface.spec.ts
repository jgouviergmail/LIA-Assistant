import { test, expect } from '../fixtures';
import type { Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { appConfig } from '../fixtures/dashboard-shell';
import { baseRoutes, sseDone } from '../fixtures/chat-approval';
import { WORLD } from '../../src/features/world/definition';
import type { WorldMessage } from '../../src/features/world/message-protocol';
import type { LiveConnectorsResponse, LiveConfigResponse } from '../../src/lib/live/types';
import en from '../../locales/en/translation.json';

const liveConnectors: LiveConnectorsResponse = {
  active_provider: 'gemini',
  connectors: [
    {
      provider: 'gemini',
      connector_type: 'gemini_live',
      status: 'active',
      active: true,
      functionally_verified: true,
      model_settings: {},
      settings: {
        model: 'fixture',
        voice: 'Puck',
        thinking_level: null,
        idle_timeout_seconds: 300,
        session_max_minutes: 15,
        session_budget_eur: null,
      },
      capabilities: {
        async_delegation: true,
        delivery_scheduling: true,
        reports_idle: true,
        cancels_on_interruption: true,
        configurable_vad: true,
        resumes: true,
        thinking: false,
        direct_tools: true,
        portal_voice: false,
        vendor_billed: false,
      },
    },
  ],
};
const liveConfig: LiveConfigResponse = {
  session_max_minutes: 15,
  session_max_bounds: { min: 1, max: 60 },
  idle_timeout_bounds: { min: 30, max: 600 },
  unlimited_value: 0,
  session_budget_eur_max: 5,
  extension_minutes: 5,
  extension_prompt_seconds: 60,
  connect_window_seconds: 30,
  idle_timeout_seconds: 300,
  hidden_grace_seconds: 30,
  standby_max_seconds: 600,
  delegation_timeout_seconds: 60,
  delegation_result_max_tokens: 1000,
  delegation_tool_name: 'lia',
  turn_text_max_chars: 2000,
  delegation_lines: {},
  direct_lines: {},
  tone_lines: {},
};

async function enter(page: Page) {
  await page.goto('/en/dashboard/world');
  await page.locator('.world-admission input[type="checkbox"]').check();
  await page.locator('.world-admission button[type="submit"]').click();
  await expect(page.locator('[data-world-status="shared"]')).toBeVisible();
}

test('world widgets: deliberate phone choices, native SMS and display mode', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  const user = await authenticate();
  await mockApi(baseRoutes(null, sseDone));
  await installInertWorldAdmission(page, user.id);
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: {
          ...appConfig.features,
          world_enabled: true,
          sms_enabled: true,
        },
      },
    },
    {
      url: '**/api/v1/sms/senders*',
      json: {
        items: [],
        total: 0,
        as_of: new Date().toISOString(),
        revision: 1,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/users/' + user.id, method: 'PATCH', json: { ...user, theme: 'dark' } },
  ]);
  await enter(page);
  const tools = page.locator('.world-device-controls');
  await tools
    .getByRole('button', {
      name: en.world.device.phone.replace('{{sms}}', '0').replace('{{reminders}}', '0'),
      exact: true,
    })
    .click();
  const phone = page.getByRole('dialog');
  await expect(phone.getByRole('button', { name: en.world.activities.call })).toBeVisible();
  await phone.getByRole('button', { name: en.sms.archive }).click();
  await expect(page.getByRole('region', { name: en.sms.title })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe('/en/dashboard/world');
  await page.keyboard.press('Escape');
  await tools
    .getByRole('button', {
      name: en.world.device.phone.replace('{{sms}}', '0').replace('{{reminders}}', '0'),
      exact: true,
    })
    .click();
  await page.getByRole('button', { name: en.world.activities.call }).click();
  await expect(page.locator('[data-world-native-panel] textarea')).toHaveValue(
    en.world.activities.call_draft
  );
  await page.keyboard.press('Escape');
  await tools.getByRole('button', { name: en.theme.to_dark }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.screenshot({ path: info.outputPath('world-hud-dark.png') });
  await tools.getByRole('button', { name: en.theme.to_oled }).click();
  await expect(page.locator('html')).toHaveAttribute('data-oled', '');
  await tools.getByRole('button', { name: en.theme.to_light }).click();
  await expect(page.locator('html')).not.toHaveClass(/dark/);
});

for (const mode of ['delegated', 'direct'] as const) {
  test(
    'world application voice: native ' + mode + ' start uses the application menu',
    async ({ page, authenticate, mockApi, browserName }) => {
      // The repository's native Live journeys use Chromium for audio hardware.
      // This exercises the real player warmup and rejects before any provider/mic call.
      test.skip(browserName !== 'chromium', 'native audio automation is Chromium-only');
      const user = await authenticate();
      await mockApi(baseRoutes(null, sseDone));
      await installInertWorldAdmission(page, user.id);
      await mockApi([
        {
          url: '**/api/v1/config',
          json: {
            ...appConfig,
            features: {
              ...appConfig.features,
              world_enabled: true,
              live_enabled: true,
            },
          },
        },
        { url: '**/api/v1/live/connectors', json: liveConnectors },
        { url: '**/api/v1/live/config', json: liveConfig },
        {
          url: '**/api/v1/live/sessions',
          method: 'POST',
          status: 409,
          json: { detail: { error_code: 'LIVE_BUSY' } },
        },
      ]);
      const starts: string[] = [];
      page.on('request', request => {
        if (request.method() !== 'POST' || !/\/live\/sessions$/.test(request.url())) return;
        const payload: unknown = request.postDataJSON();
        if (
          payload &&
          typeof payload === 'object' &&
          'mode' in payload &&
          typeof payload.mode === 'string'
        )
          starts.push(payload.mode);
      });
      await enter(page);
      await page.getByRole('banner').getByRole('button', { name: en.voice.toggle.menu }).click();
      await expect(
        page.getByRole('menuitemcheckbox', { name: en.voice.toggle.comments })
      ).toBeVisible();
      const key =
        mode === 'direct' ? en.voice.toggle.live_direct_start : en.voice.toggle.live_start;
      await page
        .getByRole('menuitem', { name: key.replace('{{provider}}', 'Gemini'), exact: true })
        .click();
      await expect.poll(() => starts).toEqual([mode]);
      await expect(page.locator('[data-world-native-panel]')).toHaveCount(0);
      await expect(page).toHaveURL(/\/dashboard\/chat(?:[?#]|$)/);
    }
  );
}

test('world conversations: per-person unread counts, private drafts, mobile list/detail and safe previews', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  const user = await authenticate();
  const peers = [
    { id: '5010c2c2-4bd0-4d21-9c08-b4502db25001', alias: 'Camille' },
    { id: '5010c2c2-4bd0-4d21-9c08-b4502db25002', alias: 'Noémie' },
  ];
  await installInertWorldAdmission(page, user.id, {
    actors: peers.map((person, i) => ({
      ...person,
      position: { x: WORLD.spawn.x + i + 1, y: WORLD.spawn.y + 2 },
      facing: 1,
      walking: false,
    })),
  });
  const now = Date.now() / 1000;
  const messages: WorldMessage[] = peers.map((peer, index) => ({
    id: '7010c2c2-4bd0-4d21-9c08-' + String(index).padStart(12, '0'),
    sender_id: peer.id,
    sender_alias: peer.alias,
    recipient_id: user.id,
    recipient_alias: 'Explorer',
    outgoing: false,
    original: 'SECRET ORIGINAL ' + peer.alias,
    text: index ? 'Hello from Noémie' : null,
    language: 'en',
    status: index ? 'original' : 'pending',
    created_at: now,
    expires_at: now + 1800,
    receipt: null,
  }));
  await mockApi([
    {
      url: '**/api/v1/world/messages/read',
      json: {
        server_time: now,
        ttl_seconds: 1800,
        truncated: false,
        messages,
      },
    },
  ]);
  await enter(page);
  await expect(
    page.getByRole('button', { name: en.world.messages.action })
  ).toHaveAccessibleDescription('Unread messages: 2');
  await page.getByRole('button', { name: en.world.messages.action }).click();
  const dock = page.locator('[data-world-messages]');
  const directory = dock.getByRole('navigation', { name: en.world.messages.conversations });
  await expect(dock.getByRole('log')).toHaveCount(0);
  await expect(dock).not.toContainText('SECRET ORIGINAL');
  await directory.getByRole('button', { name: /^Camille/ }).click();
  const field = dock.getByRole('textbox', { name: en.world.messages.message });
  await field.fill('Camille-only draft');
  await expect(dock.getByRole('log')).not.toContainText('Hello from Noémie');
  await directory.getByRole('button', { name: /^Noémie/ }).click();
  await expect(field).toHaveValue('');
  await field.fill('Noémie-only draft');
  await directory.getByRole('button', { name: /^Camille/ }).click();
  await expect(field).toHaveValue('Camille-only draft');
  await page.screenshot({ path: info.outputPath('world-conversations-desktop.png') });
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await dock.getByRole('button', { name: en.world.messages.conversations, exact: true }).click();
    await expect(directory).toBeVisible();
    await directory.getByRole('button', { name: /^Noémie/ }).click();
    await expect(field).toHaveValue('Noémie-only draft');
    await expect(dock.getByRole('log')).toContainText('Hello from Noémie');
    await page.screenshot({ path: info.outputPath('world-conversations-' + width + '.png') });
  }
});

test('world home: colours only, immediate preview, explicit save and cancellation', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  const home = {
    owner_id: user.id,
    needs_reset: false,
    preferences: {
      version: 1,
      revision: 0,
      palette: 'auto',
    },
    decoration: {
      automatic_palette: 'clay',
      palette: 'clay',
    },
  };
  let writes = 0;
  await mockApi([{ url: '**/api/v1/world/home', method: 'GET', json: home }]);
  await page.route('**/api/v1/world/home', async route => {
    if (route.request().method() !== 'PUT') return route.fallback();
    const body: unknown = route.request().postDataJSON();
    expect(body).toEqual({
      palette: 'teal',

      expected_revision: 0,
    });
    writes++;
    await route.fulfill({
      json: {
        ...home,
        preferences: {
          ...home.preferences,
          revision: 1,
          palette: 'teal',
        },
        decoration: { ...home.decoration, palette: 'teal' },
      },
    });
  });
  await enter(page);
  await page.getByRole('button', { name: en.world.home.open }).click();
  let editor = page.getByRole('dialog', { name: en.world.home.title });
  await expect(editor.getByRole('radio')).toHaveCount(7);
  await expect(editor.getByRole('checkbox')).toHaveCount(0);
  await editor.getByRole('radio', { name: en.world.home.palettes.sage, exact: true }).check();
  await editor.getByRole('button', { name: en.world.home.cancel, exact: true }).click();
  expect(writes).toBe(0);
  await page.getByRole('button', { name: en.world.home.open }).click();
  editor = page.getByRole('dialog', { name: en.world.home.title });
  await editor.getByRole('radio', { name: en.world.home.palettes.teal, exact: true }).check();
  await page.screenshot({ path: info.outputPath('world-home-palette-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: info.outputPath('world-home-palette-mobile.png') });
  await editor.getByRole('button', { name: en.world.home.save, exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(writes).toBe(1);
});

test('world voice menu: native modes and spoken preference stay available without starting a session', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ voice_enabled: true });
  await installInertWorldAdmission(page, user.id);
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, world_enabled: true, live_enabled: true },
      },
    },
    { url: '**/api/v1/live/connectors', json: liveConnectors },
    {
      url: '**/api/v1/auth/me/voice-preference',
      method: 'PATCH',
      handler: async route => {
        expect(route.request().postDataJSON()).toEqual({ voice_enabled: false });
        await mockApi([{ url: '**/api/v1/auth/me', json: { ...user, voice_enabled: false } }]);
        await route.fulfill({ status: 200, json: { voice_enabled: false } });
      },
    },
  ]);
  await enter(page);
  const voice = page.getByRole('banner').getByRole('button', { name: en.voice.toggle.menu });
  await voice.click();
  await expect(
    page.getByRole('menuitem', {
      name: en.voice.toggle.live_start.replace('{{provider}}', 'Gemini'),
      exact: true,
    })
  ).toBeEnabled();
  await expect(
    page.getByRole('menuitem', {
      name: en.voice.toggle.live_direct_start.replace('{{provider}}', 'Gemini'),
      exact: true,
    })
  ).toBeEnabled();
  const comments = page.getByRole('menuitemcheckbox', { name: en.voice.toggle.comments });
  await expect(comments).toBeChecked();
  const changed = page.waitForResponse(
    response =>
      response.url().endsWith('/auth/me/voice-preference') &&
      response.request().method() === 'PATCH'
  );
  await comments.click();
  expect((await changed).status()).toBe(200);
  await voice.click();
  await expect(comments).not.toBeChecked();
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-world-native-panel]')).toHaveCount(0);
});

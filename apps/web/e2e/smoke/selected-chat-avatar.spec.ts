/** Selected native skins on real message rows; API history stays hermetic. */
import type { Locator, Page, TestInfo } from '@playwright/test';
import { test, expect, chatRoutes, waitForHydration, type MockRoute } from '../fixtures';
import en from '../../locales/en/translation.json';
import type { ConversationMessage } from '../../src/types/conversation-message';
import type { PsycheStateSummary } from '../../src/types/psyche';

const HISTORY_ID = 'selected-avatar-history';
const LATEST_ID = 'selected-avatar-latest';
const PREFS_KEY = 'lia_eyes_widget_prefs';
const STYLES = ['smiley', 'moss', 'lumen', 'cozmo', 'spirit'] as const;
type SelectedStyle = (typeof STYLES)[number];
type Variant = 'male' | 'female';

function snapshot(mood: PsycheStateSummary['mood_label']): PsycheStateSummary {
  return {
    mood_label: mood,
    mood_color: '#8b9dc3',
    mood_pleasure: 0.25,
    mood_arousal: 0.1,
    mood_dominance: 0.15,
    active_emotion: null,
    emotion_intensity: 0,
    relationship_stage: 'ORIENTATION',
  };
}

function savedMessage(overrides: Partial<ConversationMessage>): ConversationMessage {
  return {
    id: 'selected-avatar-saved',
    role: 'assistant',
    content: '',
    created_at: '2026-10-08T08:00:00Z',
    message_metadata: null,
    tokens_in: null,
    tokens_out: null,
    tokens_cache: null,
    cost_eur: null,
    google_api_requests: null,
    stt_provider: null,
    stt_audio_duration_seconds: null,
    stt_cost_eur: null,
    tts_provider: null,
    tts_model: null,
    tts_characters: null,
    tts_cost_eur: null,
    ...overrides,
  };
}

function portraitRoutes(): MockRoute[] {
  const conversationId = '00000000-0000-4000-8000-0000000000ff';
  const messages = [
    savedMessage({
      id: HISTORY_ID,
      content: '<p>A saved curious answer.</p>',
      message_metadata: { psyche_state: snapshot('curious') },
    }),
    savedMessage({
      id: LATEST_ID,
      content: '<p>The latest contented answer.</p>',
      created_at: '2026-10-08T08:30:00Z',
      message_metadata: { psyche_state: snapshot('content') },
    }),
  ];
  return [
    ...chatRoutes([]),
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: conversationId,
        user_id: '00000000-0000-4000-8000-000000000001',
        title: 'Selected avatar browser qualification',
        message_count: messages.length,
        total_tokens: 0,
        created_at: '2026-10-08T08:00:00Z',
        updated_at: '2026-10-08T08:30:00Z',
      },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: messages.slice().reverse(),
        conversation_id: conversationId,
        total_count: messages.length,
        has_more: false,
        next_cursor: null,
      },
    },
  ];
}

async function preparePreference(page: Page, baseURL: string | undefined) {
  if (!baseURL) throw new Error('The hermetic app origin is required');
  // The production journey has no HMR. In Docker dev, keep its test-only
  // socket local so failed proxy upgrades cannot repeatedly reload the page.
  await page.routeWebSocket(/\/_next\/hmr(?:\?|$)/, socket => {
    socket.onMessage(() => {});
  });
  await page.context().addCookies([{ name: 'lia_gender', value: 'male', url: baseURL }]);
  await page.addInitScript(key => {
    // Initialize once, preserving choices made through the real settings UI.
    if (!localStorage.getItem(key)) {
      localStorage.setItem(
        key,
        JSON.stringify({
          state: { visible: false, style: 'smiley', size: 'lg', position: null },
          version: 0,
        })
      );
    }
  }, PREFS_KEY);
}

function portrait(page: Page, id = LATEST_ID): Locator {
  return page.locator(
    `[data-message-id="${id}"] [data-companion-portrait], [data-message-id="${id}"] [data-spirit-avatar]`
  );
}

async function setGender(page: Page, variant: Variant) {
  await page.evaluate(selected => {
    document.cookie = `lia_gender=${selected}; path=/; SameSite=Lax`;
    window.dispatchEvent(new Event('lia-gender-change'));
  }, variant);
}

async function expectPortrait(page: Page, id: string, style: SelectedStyle, variant: Variant) {
  const view = portrait(page, id);
  await expect(view).toBeVisible();
  await expect(view).toHaveAttribute('data-expression', id === HISTORY_ID ? 'attentive' : 'joy');
  {
    await expect(view).toHaveAttribute('data-companion-portrait', style);
    await expect(view).toHaveAttribute('data-portrait-variant', variant);
    await expect(view.locator('.lia-eyes')).toHaveCount(1);
    if (style === 'smiley')
      await expect(view.locator('.lia-eyes')).toHaveAttribute('data-smiley-variant', variant);
    if (style === 'moss' || style === 'lumen' || style === 'spirit')
      await expect(view.locator('[data-character]')).toHaveAttribute('data-character', style);
    if (style === 'cozmo') await expect(view.locator('.lia-monitor')).toHaveCount(1);
  }
  // The frame is 40 px; its parent's mood animation changes its viewport box.
  await expect(view).toHaveCSS('width', '40px');
  await expect(view).toHaveCSS('height', '40px');
  return view;
}

async function capturePortraits(page: Page, testInfo: TestInfo, name: string) {
  const first = await portrait(page, HISTORY_ID).boundingBox();
  const last = await portrait(page).boundingBox();
  if (!first || !last) throw new Error('Both actual message portraits must be visible');
  const viewport = page.viewportSize();
  if (!viewport) throw new Error('The browser viewport is required');
  const x = Math.max(0, Math.min(first.x, last.x) - 12);
  const y = Math.max(0, Math.min(first.y, last.y) - 12);
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({
    path,
    clip: {
      x,
      y,
      width: Math.min(520, viewport.width - x),
      height: Math.min(
        Math.max(first.y + first.height, last.y + last.height) - y + 12,
        viewport.height - y
      ),
    },
  });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

test('selected settings skin and current gender reach history and latest without replacing moods', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}, testInfo) => {
  test.setTimeout(180_000);
  await authenticate();
  await preparePreference(page, baseURL);
  await mockApi(portraitRoutes());
  await page.goto('/en/dashboard/settings?section=eyes-style', {
    waitUntil: 'domcontentloaded',
    timeout: 120_000,
  });
  for (const style of STYLES) {
    const choice = page.locator('#settings-section-eyes-style').getByRole('button', {
      name: en.eyes.styles[style].name,
      exact: true,
    });
    await expect(choice).toBeVisible({ timeout: 90_000 });
    await choice.focus();
    await page.keyboard.press('Enter');
    await expect(choice).toHaveAttribute('aria-current', 'true');
    await expect(choice).toBeFocused();
    await page
      .locator('header')
      .getByRole('link', { name: en.navigation.chat, exact: true })
      .click();
    await waitForHydration(page, `[data-message-id="${LATEST_ID}"]`);
    for (const variant of ['male', 'female'] as const) {
      await setGender(page, variant);
      const historical = await expectPortrait(page, HISTORY_ID, style, variant);
      const latest = await expectPortrait(page, LATEST_ID, style, variant);
      await expect(historical.locator('canvas')).toHaveCount(0);
      await expect(latest.locator('canvas')).toHaveCount(0);
      await expect(historical.locator('.lia-eyes')).toHaveAttribute('data-motion', 'off');
      await expect(latest.locator('.lia-eyes')).toHaveAttribute('data-motion', 'off');
    }
    if (style === 'smiley' || style === 'moss' || style === 'cozmo')
      await capturePortraits(page, testInfo, `${style}-female-history-and-latest-40px`);
    if (style !== 'spirit') await page.goBack({ waitUntil: 'domcontentloaded' });
  }
});

test('only the visible latest or hovered native portrait wakes; reduced motion and hiding release its GPU', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}, testInfo) => {
  test.setTimeout(150_000);
  await authenticate();
  await preparePreference(page, baseURL);
  await mockApi(portraitRoutes());
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/en/dashboard/chat', { waitUntil: 'domcontentloaded', timeout: 120_000 });
  await expect(page.locator(`[data-message-id="${LATEST_ID}"]`)).toBeVisible({ timeout: 90_000 });
  const historical = await expectPortrait(page, HISTORY_ID, 'smiley', 'male');
  const latest = await expectPortrait(page, LATEST_ID, 'smiley', 'male');
  await expect(latest.locator('canvas')).toHaveCount(1);
  await expect(historical.locator('canvas')).toHaveCount(0);
  await expect(historical.locator('.lia-eyes')).toHaveAttribute('data-rig-visible', 'false');
  await historical.hover();
  await expect(historical.locator('canvas')).toHaveCount(1);
  await page.mouse.move(0, 0);
  await expect(historical.locator('canvas')).toHaveCount(0);
  await expect(latest.locator('canvas')).toHaveCount(1);
  await capturePortraits(page, testInfo, 'smiley-male-animated-latest-frozen-history');

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(latest.locator('canvas')).toHaveCount(0);
  await expect(latest.locator('.lia-eyes')).toHaveAttribute('data-motion', 'off');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(latest.locator('canvas')).toHaveCount(1);
  // Controlled platform event, preserving the real playback hook and rig.
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(latest.locator('canvas')).toHaveCount(0);
  await expect(latest.locator('.lia-eyes')).toHaveAttribute('data-motion', 'off');
  await page.evaluate(() => {
    // Remove only the configurable test-owned shadows; the native readonly
    // getters remain on Document.prototype and resume supplying real state.
    if (
      !Reflect.deleteProperty(document, 'visibilityState') ||
      !Reflect.deleteProperty(document, 'hidden')
    )
      throw new Error('The controlled visibility shadows must be removable');
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(latest.locator('canvas')).toHaveCount(1);
  await expect(historical.locator('canvas')).toHaveCount(0);
});

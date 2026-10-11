/** Real local 3D frames and the actual companion; every API response is hermetic. */
import type { Locator, Page, TestInfo } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, chatRoutes, waitForHydration, type MockRoute } from '../fixtures';
import { expectSmileyProjection } from '../fixtures/smiley-projection';
import type { PsycheStateSummary } from '../../src/types/psyche';

type Variant = 'female' | 'male';
type Theme = 'light' | 'dark';
const MONITOR_STYLES = ['cozmo', 'capsules', 'billes', 'amande', 'traits', 'anneaux'] as const;
type MonitorStyle = (typeof MONITOR_STYLES)[number];
const MONITOR_SCREEN = JSON.parse(
  readFileSync(join(__dirname, '../../public/avatars/monitor/v1/manifest.json'), 'utf8')
).screen as { x: number; y: number; width: number; height: number; radius: number };

const CONVERSATION_ID = '00000000-0000-4000-8000-0000000000ff';
const HISTORY_ID = 'spirit-history';
const LATEST_ID = 'spirit-latest';

/** History's public payload, with required nullable accounting fields preserved. */
interface SavedMessage {
  id: string;
  role: 'assistant' | 'user';
  content: string;
  created_at: string;
  message_metadata: Record<string, unknown> | null;
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_cache: number | null;
  cost_eur: number | null;
  google_api_requests: number | null;
  stt_provider: string | null;
  stt_audio_duration_seconds: number | null;
  stt_cost_eur: number | null;
  tts_provider: string | null;
  tts_model: string | null;
  tts_characters: number | null;
  tts_cost_eur: number | null;
}

function savedMessage(overrides: Partial<SavedMessage>): SavedMessage {
  return {
    id: 'spirit-saved',
    role: 'assistant',
    content: '',
    created_at: '2026-10-07T08:00:00Z',
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

function portraitRoutes(longHistory = false): MockRoute[] {
  const messages = [
    savedMessage({
      id: HISTORY_ID,
      role: 'assistant',
      content: '<p>A saved curious answer.</p>',
      created_at: '2026-10-07T08:00:00Z',
      message_metadata: { psyche_state: snapshot('curious') },
    }),
    ...(longHistory
      ? Array.from({ length: 24 }, (_, index) =>
          savedMessage({
            id: `spirit-note-${index}`,
            role: 'user',
            content: `Saved note ${index + 1}: a longer conversation lets us read an older answer without replaying its animation.`,
            created_at: new Date(Date.parse('2026-10-07T08:01:00Z') + index * 60_000).toISOString(),
          })
        )
      : []),
    savedMessage({
      id: LATEST_ID,
      role: 'assistant',
      content: '<p>The latest contented answer.</p>',
      created_at: '2026-10-07T08:30:00Z',
      message_metadata: { psyche_state: snapshot('content') },
    }),
  ];
  return [
    ...chatRoutes([]),
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: CONVERSATION_ID,
        user_id: '00000000-0000-4000-8000-000000000001',
        title: 'LIA Spirit browser qualification',
        message_count: messages.length,
        total_tokens: 0,
        created_at: '2026-10-07T08:00:00Z',
        updated_at: '2026-10-07T08:30:00Z',
      },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        // The API pages newest first; useConversation restores display order.
        messages: messages.slice().reverse(),
        conversation_id: CONVERSATION_ID,
        total_count: messages.length,
        has_more: false,
        next_cursor: null,
      },
    },
  ];
}

async function preparePreference(
  page: Page,
  baseURL: string | undefined,
  variant: Variant,
  theme: Theme,
  style: 'spirit' | 'smiley' | MonitorStyle = 'spirit'
) {
  if (!baseURL) throw new Error('The hermetic app origin is required');
  await page.context().addCookies([{ name: 'lia_gender', value: variant, url: baseURL }]);
  await page.addInitScript(
    ({ selectedTheme, selectedStyle }) => {
      localStorage.setItem('theme', selectedTheme);
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: {
            visible: true,
            style: selectedStyle,
            size: 'lg',
            position: { xPct: 70, yPct: 24 },
          },
          version: 0,
        })
      );
    },
    { selectedTheme: theme, selectedStyle: style }
  );
}

function messagePortrait(page: Page, id = LATEST_ID): Locator {
  return page.locator(`[data-message-id="${id}"] [data-spirit-avatar] img`);
}

function companion(page: Page): Locator {
  return page.getByRole('group', { name: /LIA's expressive eyes/ });
}

async function expectDecoded(image: Locator, resolution = 192): Promise<void> {
  await expect(image).toHaveJSProperty('naturalWidth', resolution);
  await expect(image).toHaveJSProperty('naturalHeight', resolution);
}

async function capture(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

async function captureDetail(page: Page, face: Locator, testInfo: TestInfo, name: string) {
  const box = await face.boundingBox();
  if (!box) throw new Error('The actual companion must be visible');
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({
    path,
    clip: {
      x: box.x + box.width / 2 - 96,
      y: box.y + box.height / 2 - 96,
      width: 192,
      height: 192,
    },
  });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

async function blinkState(face: Locator) {
  return face.evaluate(element => ({
    clock: Date.now(),
    left: Number.parseFloat((element as HTMLElement).style.getPropertyValue('--rig-blink-l')),
    right: Number.parseFloat((element as HTMLElement).style.getPropertyValue('--rig-blink-r')),
    clips: [...element.querySelectorAll('.lia-eye-blink')].map(
      lid => getComputedStyle(lid).clipPath
    ),
    lidTransforms: [...element.querySelectorAll('.lia-eye-blink')].map(
      lid => getComputedStyle(lid).transform
    ),
  }));
}

async function captureBlink(page: Page, face: Locator, testInfo: TestInfo, name: string) {
  const before = await blinkState(face);
  await captureDetail(page, face, testInfo, name);
  const after = await blinkState(face);
  expect(after).toEqual(before);
  const path = testInfo.outputPath(`${name}-state.json`);
  writeFileSync(path, JSON.stringify({ before, after }, null, 2));
  await testInfo.attach(`${name}-state`, {
    path,
    contentType: 'application/json',
  });
}

/** Read the native projection at one clock tick, without altering a channel. */
async function faceProjection(face: Locator) {
  return face.evaluate(root => {
    const head = root.querySelector<HTMLElement>('.lia-head')!;
    const pair = root.querySelector<HTMLElement>('.lia-eyes-gaze')!;
    const mouth = root.querySelector<HTMLElement>('.lia-mouth')!;
    const boundary = root.querySelector<HTMLElement>('.lia-raster-face-mask, .lia-monitor-screen')!;
    const projection = (node: HTMLElement) => {
      const matrix = new DOMMatrix(getComputedStyle(node).transform);
      return { x: matrix.m41, y: matrix.m42, z: matrix.m43 };
    };
    const value = (key: string) =>
      Number.parseFloat((root as HTMLElement).style.getPropertyValue(`--rig-${key}`));
    return {
      sphere: root.classList.contains('lia-smiley'),
      sphereReady: root.querySelector('.lia-avatar-body')?.getAttribute('data-sphere-ready'),
      gazeX: value('gaze-x'),
      gazeY: value('gaze-y'),
      yaw: value('head-yaw'),
      pitch: value('head-pitch'),
      headTransform: getComputedStyle(head).transform,
      pair: projection(pair),
      mouth: projection(mouth),
      boundary: {
        inHead: boundary.parentElement === head,
        eyesInside: boundary.contains(pair),
        mouthInside: boundary.contains(mouth),
        browsOutside: !boundary.querySelector('[data-rig-brow]'),
        mask: getComputedStyle(boundary).maskImage,
        maskMode: getComputedStyle(boundary).maskMode,
        overflow: getComputedStyle(boundary).overflow,
        clip: getComputedStyle(boundary).clipPath,
      },
    };
  });
}

async function expectSharedProjection(face: Locator, raster: boolean) {
  const view = await faceProjection(face);
  expect(view.boundary.inHead).toBe(true);
  expect(view.boundary.eyesInside).toBe(true);
  expect(view.boundary.mouthInside).toBe(true);
  expect(view.boundary.browsOutside).toBe(true);
  if (raster) {
    if (view.sphere) {
      expect(view.sphereReady).toBe('true');
      expect(view.boundary.mask).toBe('none');
      expect(view.boundary.clip).toBe('circle(49%)');
      await expectSmileyProjection(face);
    } else {
      expect(view.boundary.mask).toContain('/body.webp');
      expect(view.boundary.maskMode).toBe('alpha');
    }
    expect(view.pair.x).toBeCloseTo(view.mouth.x, 3);
    expect(view.pair.y).toBeCloseTo(view.mouth.y, 3);
  } else {
    expect(view.boundary.overflow).toBe('hidden');
    expect(view.boundary.clip).toMatch(/^inset\(.*round/);
  }
  return view;
}

async function captureCornerGazes(
  page: Page,
  face: Locator,
  testInfo: TestInfo,
  name: string,
  raster: boolean
) {
  const viewport = page.viewportSize();
  if (!viewport) throw new Error('The actual desktop viewport is required');
  for (const [corner, directionX, directionY] of [
    ['top-left', -1, -1],
    ['top-right', 1, -1],
    ['bottom-left', -1, 1],
    ['bottom-right', 1, 1],
  ] as const) {
    await page.mouse.move(
      directionX < 0 ? 0 : viewport.width - 1,
      directionY < 0 ? 0 : viewport.height - 1
    );
    await page.clock.runFor(32);
    await expect
      .poll(async () => Number(await face.getAttribute('data-gaze-x')) * directionX)
      .toBeGreaterThan(0.2);
    await page.clock.runFor(640);
    const view = await expectSharedProjection(face, raster);
    expect(view.gazeX * directionX).toBeGreaterThan(0.2);
    expect(view.gazeY * directionY).toBeGreaterThan(0.05);
    expect(view.yaw * directionX).toBeGreaterThan(0.05);
    expect(view.pitch * directionY).toBeGreaterThan(0.02);
    if (!view.sphere) expect(view.headTransform).toMatch(/^matrix3d\(/);
    await captureDetail(page, face, testInfo, `${name}-gaze-${corner}-192`);
    await testInfo.attach(`${name}-gaze-${corner}-projection`, {
      body: JSON.stringify(view),
      contentType: 'application/json',
    });
  }
}

async function captureSmileyBlink(page: Page, face: Locator, testInfo: TestInfo, elapsed: number) {
  const box = await face.boundingBox();
  if (!box) throw new Error('The actual Smiley must be visible');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.clock.runFor(160);
  await page.clock.runFor(Math.max(0, 4600 - elapsed - 160));
  const phases = new Set<string>();
  let previous = 0;
  for (let frame = 0; frame < 64; frame++) {
    await page.clock.runFor(16);
    const state = await blinkState(face);
    // Three dimensional iris artwork is clipped, never vertically crushed.
    expect(state.lidTransforms).toEqual(['none', 'none']);
    let phase: string | null = null;
    if (state.left > previous + 0.02 && state.left > 0.1 && state.left < 0.5)
      phase = 'closing-quarter';
    if (state.left > previous + 0.02 && state.left >= 0.5 && state.left < 0.94)
      phase = 'closing-half';
    if (state.left > 0.94) phase = 'closed-left';
    if (state.right > 0.94 && phases.has('closed-left')) phase = 'closed-right';
    if (state.left < previous - 0.02 && state.left > 0.1 && state.left < 0.8)
      phase = 'reopening-half';
    if (phase && !phases.has(phase)) {
      phases.add(phase);
      await expectSharedProjection(face, true);
      await captureBlink(page, face, testInfo, `smiley-blink-${phase}-192`);
    }
    previous = state.left;
  }
  expect(phases.has('closing-quarter')).toBe(true);
  expect(phases.has('closing-half')).toBe(true);
  expect(phases.has('closed-left')).toBe(true);
  expect(phases.has('closed-right')).toBe(true);
  expect(phases.has('reopening-half')).toBe(true);
  const reopened = await blinkState(face);
  expect(Math.abs(reopened.left)).toBeLessThan(0.05);
  expect(Math.abs(reopened.right)).toBeLessThan(0.05);
  await captureBlink(page, face, testInfo, 'smiley-blink-reopened-192');
}

async function expectSpiritTextures(face: Locator, variant: Variant) {
  const sources = await face.evaluate(async element => {
    const head = element.querySelector<HTMLElement>('.lia-head')!;
    const graphics = [
      [head, '::before', 'backgroundImage'],
      [element.querySelector('.lia-eye--left .lia-eye-shape')!, null, 'backgroundImage'],
      [element.querySelector('.lia-eye--right .lia-eye-shape')!, null, 'backgroundImage'],
      [element.querySelector('.lia-eye-pupil')!, null, 'backgroundImage'],
      [element.querySelector('.lia-eye--left .lia-eye-pupil-clip')!, null, 'maskImage'],
      [element.querySelector('.lia-eye--right .lia-eye-pupil-clip')!, null, 'maskImage'],
    ] as const;
    return Promise.all(
      graphics.map(async ([graphic, pseudo, property]) => {
        const background = getComputedStyle(graphic, pseudo)[property];
        const source = background.match(/^url\(["']?(.*?)["']?\)$/)?.[1];
        if (!source) throw new Error('The original 3D texture must be mounted');
        const image = new Image();
        image.src = source;
        await image.decode();
        return {
          url: new URL(source).pathname,
          width: image.naturalWidth,
          height: image.naturalHeight,
        };
      })
    );
  });
  expect(sources.map(source => source.url)).toEqual([
    `/avatars/spirit/v1/${variant}/body.webp`,
    `/avatars/spirit/v1/${variant}/eye.webp`,
    `/avatars/spirit/v1/${variant}/eye-right.webp`,
    `/avatars/spirit/v1/${variant}/iris.webp`,
    `/avatars/spirit/v1/${variant}/sclera-mask.webp`,
    `/avatars/spirit/v1/${variant}/sclera-mask-right.webp`,
  ]);
  expect(sources[0]).toMatchObject({ width: 192, height: 192 });
  for (const organ of sources.slice(1)) expect(organ).toMatchObject({ width: 128, height: 128 });
  await expect(face.locator('.lia-eye-shape')).toHaveCount(2);
  await expect(face.locator('.lia-eye-pupil-clip')).toHaveCount(2);
  await expect(face.locator('[data-rig-mouth]')).toHaveCount(1);
  await expect(face.locator('[data-rig-brow]')).toHaveCount(2);
}

for (const [variant, theme] of [
  ['female', 'light'],
  ['male', 'dark'],
] as const) {
  test(`${variant} spirit renders real frames in ${theme}, with bounded playback and sizes`, async ({
    page,
    authenticate,
    mockApi,
    baseURL,
  }, testInfo) => {
    await authenticate({ theme });
    await preparePreference(page, baseURL, variant, theme);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await mockApi(portraitRoutes());
    await page.addInitScript(() => {
      Math.random = () => 0.99;
    });
    await page.clock.install({ time: new Date('2026-10-07T12:00:00Z') });
    await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
    await page.goto('/en/dashboard/chat');
    const latest = messagePortrait(page);
    const historical = messagePortrait(page, HISTORY_ID);
    const face = companion(page).locator(`[data-spirit-companion="${variant}"] .lia-spirit-rig`);
    await expect(face).toBeVisible();
    await waitForHydration(page, '.lia-spirit-rig');
    await expect(latest).toHaveAttribute('src', `/avatars/spirit/v1/compact/${variant}/joy.webp`);
    await expect(historical).toHaveAttribute(
      'src',
      `/avatars/spirit/v1/compact/${variant}/attentive-still.webp`
    );
    await expectDecoded(latest, 96);
    await expectSpiritTextures(face, variant);
    await expect(face).toHaveAttribute('data-expression', 'neutral');
    await expectSharedProjection(face, true);
    await captureDetail(page, face, testInfo, `spirit-${variant}-neutral-192`);
    const clockBeforeGaze = await page.evaluate(() => Date.now());
    await captureCornerGazes(page, face, testInfo, `spirit-${variant}`, true);
    // Return to the companion's actual center before the physiological blink.
    const resting = await face.boundingBox();
    if (!resting) throw new Error('The companion must stay in the viewport');
    await page.mouse.move(resting.x + resting.width / 2, resting.y + resting.height / 2);
    await page.clock.runFor(160);
    // Advance the real native scheduler into its first physiological blink.
    // The authored textures stay intact while both lid masks close together.
    const gazeDuration = (await page.evaluate(() => Date.now())) - clockBeforeGaze;
    await page.clock.runFor(Math.max(0, 4600 - gazeDuration));
    let halfBlink = false;
    let leftPeak = 0;
    let rightPeak = 0;
    let closedLeft = false;
    let closedRight = false;
    let closedTogether = false;
    let pairedPeak = 0;
    for (let frame = 0; frame < 60; frame++) {
      await page.clock.runFor(16);
      const { left, right } = await blinkState(face);
      leftPeak = Math.max(leftPeak, left);
      rightPeak = Math.max(rightPeak, right);
      pairedPeak = Math.max(pairedPeak, Math.min(left, right));
      // The native right lid deliberately trails the left by 70 ms.
      // Their partial closure windows do not overlap; observe each real tape.
      if (!halfBlink && ((left > 0.68 && left < 0.88) || (right > 0.68 && right < 0.88))) {
        halfBlink = true;
        await captureBlink(page, face, testInfo, `spirit-${variant}-blink-half-192`);
      }
      if (!closedLeft && left > 0.94) {
        closedLeft = true;
        await captureBlink(page, face, testInfo, `spirit-${variant}-blink-closed-left-192`);
      }
      if (!closedRight && right > 0.94) {
        closedRight = true;
        await captureBlink(page, face, testInfo, `spirit-${variant}-blink-closed-right-192`);
      }
      if (!closedTogether && left > 0.94 && right > 0.94) {
        closedTogether = true;
        await captureBlink(page, face, testInfo, `spirit-${variant}-blink-closed-both-192`);
      }
    }
    expect(halfBlink).toBe(true);
    expect(leftPeak).toBeGreaterThan(0.5);
    expect(rightPeak).toBeGreaterThan(0.5);
    expect(closedLeft).toBe(true);
    expect(closedRight).toBe(true);
    await captureBlink(page, face, testInfo, `spirit-${variant}-blink-reopened-192`);
    await testInfo.attach(`spirit-${variant}-blink-peaks`, {
      body: JSON.stringify({ leftPeak, rightPeak, pairedPeak, closedTogether }),
      contentType: 'application/json',
    });
    const messageBox = await latest.boundingBox();
    const companionBox = await face.boundingBox();
    if (!messageBox || !companionBox) throw new Error('Both real portraits must be visible');
    expect(messageBox.width).toBeCloseTo(40, 1);
    expect(messageBox.height).toBeCloseTo(40, 1);
    expect(companionBox.width).toBeCloseTo(114.4, 1);
    expect(companionBox.height).toBeCloseTo(114.4, 1);
    await page.locator(`[data-message-id="${HISTORY_ID}"] [data-spirit-avatar]`).hover();
    await expect(historical).toHaveAttribute(
      'src',
      `/avatars/spirit/v1/compact/${variant}/attentive.webp`
    );
    await page.mouse.move(0, 0);
    await expect(historical).toHaveAttribute(
      'src',
      `/avatars/spirit/v1/compact/${variant}/attentive-still.webp`
    );
    await page.emulateMedia({ reducedMotion: 'reduce' });
    // The real rig writes its settled pose on the next shared animation frame.
    await page.clock.runFor(32);
    await expect(latest).toHaveAttribute(
      'src',
      `/avatars/spirit/v1/compact/${variant}/joy-still.webp`
    );
    await expectDecoded(latest, 96);
    await expectSpiritTextures(face, variant);
    for (let tick = 0; tick < 15; tick++) {
      const current = await blinkState(face);
      if (current.left === 0 && current.right === 0) break;
      await page.clock.runFor(32);
    }
    const settled = await blinkState(face);
    expect(settled.left).toBe(0);
    expect(settled.right).toBe(0);
    expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(
      true
    );
    await page.clock.runFor(240);
    const stable = await blinkState(face);
    expect({ left: stable.left, right: stable.right, clips: stable.clips }).toEqual({
      left: settled.left,
      right: settled.right,
      clips: settled.clips,
    });
    await expect(page.locator('html')).toHaveClass(new RegExp(`(?:^|\\s)${theme}(?:\\s|$)`));
    await capture(page, testInfo, `spirit-${variant}-${theme}`);
  });
}

test('spirit keeps keyboard movement, size cycling, hide/restore and the message breakpoint', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}) => {
  await authenticate();
  await preparePreference(page, baseURL, 'male', 'light');
  await mockApi(portraitRoutes());
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);
  const widget = companion(page);
  const face = widget.locator('[data-spirit-companion="male"] .lia-spirit-rig');
  await expectSpiritTextures(face, 'male');
  await widget.focus();
  const before = await widget.boundingBox();
  if (!before) throw new Error('The floating controls must be visible');
  await page.keyboard.press('ArrowLeft');
  await expect.poll(async () => (await widget.boundingBox())?.x).toBeLessThan(before.x);
  await widget.getByRole('button', { name: 'Change the eyes size', exact: true }).click();
  await expect(face).toHaveClass(/lia-eyes--sm/);
  await expect(face).toHaveCSS('font-size', '20px');
  await expect
    .poll(() => face.evaluate(element => element.getBoundingClientRect().width))
    .toBeCloseTo(52, 1);
  await widget.getByRole('button', { name: 'Hide the eyes', exact: true }).click();
  await expect(widget).toHaveCount(0);
  await page.getByRole('button', { name: 'Show the eyes', exact: true }).click();
  await expect(face).toBeVisible();
  await expect(face).toHaveClass(/lia-eyes--sm/);
  await expect(face).toHaveCSS('font-size', '20px');
  await expect
    .poll(() => face.evaluate(element => element.getBoundingClientRect().width))
    .toBeCloseTo(52, 1);
  expect(
    await page.evaluate(
      () => JSON.parse(localStorage.getItem('lia_eyes_widget_prefs') ?? '{}').state.style
    )
  ).toBe('spirit');
  await page.setViewportSize({ width: 879, height: 900 });
  await expect(messagePortrait(page)).not.toBeVisible();
  await page.setViewportSize({ width: 880, height: 900 });
  await expect(messagePortrait(page)).toBeVisible();
  await expectDecoded(messagePortrait(page), 96);
});

test('a real scroll suspends the latest clip and returning resumes it', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}) => {
  await authenticate();
  await preparePreference(page, baseURL, 'female', 'light');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await mockApi(portraitRoutes(true));
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);
  const latest = messagePortrait(page);
  const latestMessage = page.locator(`[data-message-id="${LATEST_ID}"]`);
  await latestMessage.scrollIntoViewIfNeeded();
  await expect(latest).toHaveAttribute('src', '/avatars/spirit/v1/compact/female/joy.webp');
  await expectDecoded(latest, 96);
  // A real reader gesture cancels the initial bottom pin; a programmatic
  // scroll alone can race that pin while the history is settling.
  await page.locator(`[data-message-id="${LATEST_ID}"]`).hover();
  await page.mouse.wheel(0, -900);
  await page.locator(`[data-message-id="${HISTORY_ID}"]`).scrollIntoViewIfNeeded();
  await expect(latest).not.toBeInViewport();
  await expect(latest).toHaveAttribute('src', '/avatars/spirit/v1/compact/female/joy-still.webp');
  await latestMessage.scrollIntoViewIfNeeded();
  await expect(latest).toHaveAttribute('src', '/avatars/spirit/v1/compact/female/joy.webp');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(latest).toHaveAttribute('src', '/avatars/spirit/v1/compact/female/joy-still.webp');
});

for (const style of MONITOR_STYLES) {
  test(`${style} monitor keeps its native face inside the original 3D display`, async ({
    page,
    authenticate,
    mockApi,
    baseURL,
  }, testInfo) => {
    await authenticate();
    await preparePreference(page, baseURL, 'female', 'light', style);
    await mockApi(chatRoutes([]));
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.addInitScript(() => {
      Math.random = () => 0.99;
    });
    await page.clock.install({ time: new Date('2026-10-07T12:00:00Z') });
    await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
    await page.goto('/en/dashboard/chat');
    const face = companion(page).locator(`.lia-monitor[data-style="${style}"]`);
    await expect(face).toBeVisible();
    await waitForHydration(page, '.lia-monitor');
    await expect(face).toHaveAttribute('data-expression', 'neutral');
    const geometry = await face.evaluate(async element => {
      const head = element.querySelector<HTMLElement>('.lia-head')!;
      const screen = element.querySelector<HTMLElement>('.lia-monitor-screen')!;
      const brows = element.querySelector<HTMLElement>('.lia-monitor-brows')!;
      const frame = element.getBoundingClientRect();
      const display = screen.getBoundingClientRect();
      const mask = getComputedStyle(screen);
      // Screen coordinates belong to the common head before perspective.
      // A rotated screen's viewport AABB is not its source-image rectangle.
      const headStyle = getComputedStyle(head);
      const headWidth = Number.parseFloat(headStyle.width);
      const headHeight = Number.parseFloat(headStyle.height);
      const background = getComputedStyle(head, '::before').backgroundImage;
      const source = background.match(/^url\(["']?(.*?)["']?\)$/)?.[1];
      if (!source) throw new Error('The real monitor body must be mounted');
      const image = new Image();
      image.src = source;
      await image.decode();
      const paint = [...screen.querySelectorAll('.lia-eye-shape, [data-rig-mouth]')].map(
        graphic => {
          const rect = graphic.getBoundingClientRect();
          return {
            left: rect.left - display.left,
            top: rect.top - display.top,
            right: rect.right - display.left,
            bottom: rect.bottom - display.top,
          };
        }
      );
      return {
        width: frame.width,
        height: frame.height,
        x: Number.parseFloat(mask.left) / headWidth,
        y: Number.parseFloat(mask.top) / headHeight,
        screenWidth: Number.parseFloat(mask.width) / headWidth,
        screenHeight: Number.parseFloat(mask.height) / headHeight,
        radius: Number.parseFloat(mask.borderTopLeftRadius) / headWidth,
        displayWidth: display.width,
        displayHeight: display.height,
        overflow: mask.overflow,
        clip: mask.clipPath,
        asset: source,
        pixels: [image.naturalWidth, image.naturalHeight],
        browsOutside: !screen.contains(brows) && !screen.querySelector('.lia-eye-brow'),
        eyeCount: screen.querySelectorAll('.lia-eye-shape').length,
        mouthCount: screen.querySelectorAll('[data-rig-mouth]').length,
        browCount: brows.querySelectorAll('[data-rig-brow]').length,
        paint,
      };
    });
    expect(geometry.width).toBeCloseTo(114.4, 1);
    expect(geometry.height).toBeCloseTo(114.4, 1);
    expect(geometry.x).toBeCloseTo(MONITOR_SCREEN.x, 2);
    expect(geometry.y).toBeCloseTo(MONITOR_SCREEN.y, 2);
    expect(geometry.screenWidth).toBeCloseTo(MONITOR_SCREEN.width, 2);
    expect(geometry.screenHeight).toBeCloseTo(MONITOR_SCREEN.height, 2);
    expect(geometry.radius).toBeCloseTo(MONITOR_SCREEN.radius, 2);
    expect(geometry.overflow).toBe('hidden');
    expect(geometry.clip).toMatch(/^inset\(.*round/);
    expect(geometry.asset).toContain('/avatars/monitor/v1/body.webp');
    expect(geometry.pixels).toEqual([192, 192]);
    expect(geometry.browsOutside).toBe(true);
    expect(geometry.eyeCount).toBe(2);
    expect(geometry.mouthCount).toBe(1);
    expect(geometry.browCount).toBe(2);
    for (const graphic of geometry.paint) {
      expect(graphic.left).toBeGreaterThanOrEqual(-0.5);
      expect(graphic.top).toBeGreaterThanOrEqual(-0.5);
      expect(graphic.right).toBeLessThanOrEqual(geometry.displayWidth + 0.5);
      expect(graphic.bottom).toBeLessThanOrEqual(geometry.displayHeight + 0.5);
    }
    if (['cozmo', 'billes', 'anneaux'].includes(style)) {
      await captureDetail(page, face, testInfo, `monitor-${style}-neutral-192`);
    }
    await captureCornerGazes(page, face, testInfo, `monitor-${style}`, false);
  });
}

test('smiley projects its original sphere and keeps facial organs within the body', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}, testInfo) => {
  await authenticate();
  await preparePreference(page, baseURL, 'female', 'light', 'smiley');
  await mockApi(chatRoutes([]));
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.addInitScript(() => {
    Math.random = () => 0.99;
  });
  await page.clock.install({ time: new Date('2026-10-07T12:00:00Z') });
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
  await page.goto('/en/dashboard/chat');
  const face = companion(page).locator('.lia-eyes[data-style="smiley"]');
  await expect(face).toBeVisible();
  await waitForHydration(page, '.lia-eyes[data-style="smiley"]');
  for (
    let frame = 0;
    frame < 20 &&
    (await face.locator('.lia-avatar-body').getAttribute('data-sphere-ready')) !== 'true';
    frame++
  ) {
    await page.clock.runFor(32);
  }
  await expect(face.locator('.lia-avatar-body')).toHaveAttribute('data-sphere-ready', 'true');
  await expect(face).toHaveAttribute('data-smiley-variant', 'female');
  const assets = await face.evaluate(async root => {
    const urls = new Set<string>();
    for (const node of [root, ...root.querySelectorAll('*')]) {
      for (const pseudo of [null, '::before', '::after']) {
        const css = getComputedStyle(node, pseudo);
        for (const paint of [css.backgroundImage, css.maskImage]) {
          for (const match of paint.matchAll(/url\(["']?(.*?)["']?\)/g)) {
            if (new URL(match[1]).pathname.startsWith('/avatars/smiley/v1/')) urls.add(match[1]);
          }
        }
      }
    }
    return Promise.all(
      [...urls].map(async source => {
        const image = new Image();
        image.src = source;
        await image.decode();
        return {
          url: new URL(source).pathname,
          width: image.naturalWidth,
          height: image.naturalHeight,
        };
      })
    );
  });
  expect(assets.map(asset => asset.url).sort()).toEqual([
    '/avatars/smiley/v1/body.webp',
    '/avatars/smiley/v1/bow.webp',
    '/avatars/smiley/v1/eye.webp',
    '/avatars/smiley/v1/iris.webp',
    '/avatars/smiley/v1/sclera-mask.webp',
  ]);
  expect(assets.find(asset => asset.url.endsWith('/body.webp'))).toMatchObject({
    width: 192,
    height: 192,
  });
  for (const organ of assets.filter(asset => !asset.url.endsWith('/body.webp')))
    expect(organ).toMatchObject({ width: 128, height: 128 });
  await expect(face.locator('.lia-eye-pupil-clip')).toHaveCount(2);
  await expect(face.locator('[data-rig-mouth]')).toHaveCount(1);
  await expect(face.locator('[data-rig-brow-shape="sculpted"]')).toHaveCount(2);
  await expectSharedProjection(face, true);
  await captureDetail(page, face, testInfo, 'smiley-neutral-192');
  const gazeBegan = await page.evaluate(() => Date.now());
  await captureCornerGazes(page, face, testInfo, 'smiley', true);
  const elapsed = (await page.evaluate(() => Date.now())) - gazeBegan;
  await captureSmileyBlink(page, face, testInfo, elapsed);
});

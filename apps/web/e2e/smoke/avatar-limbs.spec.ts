/** Real native rendering and interaction, with every backend request isolated. */
import type { Locator, Page, TestInfo } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import {
  test,
  expect,
  chatRoutes,
  loadedChatRoutes,
  idleNotificationStream,
  waitForClockedHydration,
  type MockRoute,
} from '../fixtures';
import { CHANNELS, LIMB_CHANNELS, type LimbChannel } from '../../src/components/eyes/rig/channels';
import { limbProfile } from '../../src/components/eyes/volume/limb-profiles';
import { companionBodyAsset } from '../../src/components/spirit/companion-catalogue';
import type { PsycheStateSummary } from '../../src/types/psyche';

const CHARACTERS = ['spirit', 'moss', 'lumen', 'nimbo', 'bip', 'boulon', 'oscar'] as const;
type Character = (typeof CHARACTERS)[number] | 'orbit';
type Variant = 'female' | 'male';
const LIMB_PROPERTIES = LIMB_CHANNELS.map(channel => CHANNELS[channel].cssVar);
// This production life seed exercises both directions of the natural
// free-foot beats. Development remounts consume another construction salt.
const LIFE_FIXTURE_TIME = '2026-11-07T12:00:23.857Z';
const SAVED_PSYCHE: PsycheStateSummary = {
  mood_label: 'curious',
  mood_color: '#8b9dc3',
  mood_pleasure: 0.25,
  mood_arousal: 0.1,
  mood_dominance: 0.15,
  active_emotion: null,
  emotion_intensity: 0,
  relationship_stage: 'ORIENTATION',
};

/** Nominal empty chat: an unrelated shell request must not become an error cue. */
function companionRoutes(): MockRoute[] {
  return [
    ...chatRoutes([]),
    idleNotificationStream,
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    { url: '**/api/v1/skills', json: { skills: [], total: 0 } },
    { url: '**/api/v1/chat/shortcuts', json: { shortcuts: [], max_count: 0 } },
    { url: '**/api/v1/chat/suggestions', json: { suggestions: [] } },
    {
      url: '**/api/v1/system-settings/debug-panel-status',
      json: { enabled: false, user_access_available: false },
    },
    {
      url: '**/api/v1/psyche/settings',
      json: {
        psyche_enabled: true,
        psyche_display_avatar: true,
        psyche_sensitivity: 50,
        psyche_stability: 50,
      },
    },
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: '00000000-0000-4000-8000-0000000000ff',
        user_id: '00000000-0000-4000-8000-000000000001',
        title: 'Native avatar qualification',
        message_count: 0,
        total_tokens: 0,
        created_at: '2026-11-07T10:00:00Z',
        updated_at: '2026-11-07T10:00:00Z',
      },
    },
  ];
}

async function expectSourceFallback(face: Locator) {
  const fallback = await face.locator('.lia-head').evaluate(head => {
    const style = getComputedStyle(head, '::before');
    return { image: style.backgroundImage, visibility: style.visibility };
  });
  expect(fallback.image).toContain(companionBodyAsset('bip', 'female'));
  expect(fallback.visibility).toBe('visible');
  await expect(face.locator('[data-volume-canvas]')).toBeHidden();
}

async function prepare(
  page: Page,
  baseURL: string | undefined,
  character: Character,
  variant: Variant
) {
  if (!baseURL) throw new Error('The hermetic app origin is required');
  await page.context().addCookies([{ name: 'lia_gender', value: variant, url: baseURL }]);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.addInitScript(selected => {
    localStorage.setItem('theme', 'light');
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({
        state: { visible: true, style: selected, size: 'lg', position: { xPct: 70, yPct: 24 } },
        version: 0,
      })
    );
    // Observe real draws, forwarding the untouched arguments to the native GPU.
    const original = WebGLRenderingContext.prototype.drawElements;
    WebGLRenderingContext.prototype.drawElements = function (...args) {
      const result = original.apply(this, args);
      if (this.canvas instanceof HTMLCanvasElement) {
        const previous = Number(this.canvas.dataset.e2eNativeDraws ?? 0);
        this.canvas.dataset.e2eNativeDraws = String(previous + 1);
        if (this.canvas.dataset.e2eCaptureBoundary === 'true') {
          // Read before the non-preserved drawing buffer is composited/cleared.
          // Retain the last real draw within an explicitly sampled interval:
          // a settled non-articulated body may stop drawing before its end.
          const { width, height } = this.canvas;
          const pixels = new Uint8Array(width * height * 4);
          this.readPixels(0, 0, width, height, this.RGBA, this.UNSIGNED_BYTE, pixels);
          let minX = width,
            minY = height,
            maxX = -1,
            maxY = -1,
            painted = 0;
          for (let y = 0; y < height; y++)
            for (let x = 0; x < width; x++) {
              // The reviewed WebPs carry alpha2 in nominally blank areas.
              if (pixels[(y * width + x) * 4 + 3] < 16) continue;
              painted++;
              minX = Math.min(minX, x);
              minY = Math.min(minY, y);
              maxX = Math.max(maxX, x);
              maxY = Math.max(maxY, y);
            }
          Object.assign(this.canvas.dataset, {
            e2ePaintedDraw: String(previous + 1),
            e2ePainted: String(painted),
            e2eMinX: String(minX),
            e2eMinY: String(minY),
            e2eMaxX: String(maxX),
            e2eMaxY: String(maxY),
          });
        }
      }
      return result;
    };
    // Keep the host's calm/lively gesture draw in its quiet flicker slot. The
    // native mouth and limb life stream retains its separate seed and clock.
    // Distinct draws still give React distinct renderer identifiers.
    let seed = 0x12345678;
    Math.random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return 0.9 + (seed / 0x100000000) * 0.009;
    };
  }, character);
  await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10_000));
  // Native life seeds from Date.now at construction. Network/hydration latency
  // must not choose a different performance; timers and RAF remain clocked.
  await page.clock.setFixedTime(new Date(LIFE_FIXTURE_TIME));
}

async function openCompanion(page: Page, character: Character, variant: Variant): Promise<Locator> {
  const response = await page.goto('/en/dashboard/chat');
  expect(response?.status(), 'The local app server must serve the chat').toBe(200);
  const identity = page
    .getByRole('group', { name: /LIA's expressive eyes/ })
    .locator(`[data-character="${character}"]`);
  const face = identity.locator('.lia-eyes');
  await waitForClockedHydration(page, face);
  await expect(identity).toHaveAttribute('data-spirit-companion', variant);
  await expect
    .poll(() =>
      face.locator('.lia-head').evaluate(head => getComputedStyle(head, '::before').backgroundImage)
    )
    .toContain(companionBodyAsset(character, variant));
  await expect
    .poll(async () => {
      await page.clock.runFor(32);
      return face.getAttribute('data-volume-ready');
    })
    .toBe('true');
  await page.clock.setSystemTime(new Date(LIFE_FIXTURE_TIME));
  await page.mouse.move(0, 0);
  await advancePose(page, face, 640);
  return face;
}

/** Read the shader's actual joint angles, not a mocked upload or data attribute. */
async function paintedPose(face: Locator) {
  return face.evaluate((root, properties) => {
    const canvas = root.querySelector<HTMLCanvasElement>('[data-volume-canvas]');
    const gl = canvas?.getContext('webgl');
    const program = gl?.getParameter(gl.CURRENT_PROGRAM);
    if (!canvas || !gl || !program) throw new Error('The real native volume must be drawing');
    const angles = properties.map((_, index) => {
      const location = gl.getUniformLocation(program, `u_joints[${index}]`);
      if (!location) return null;
      const value = gl.getUniform(program, location);
      if (!(value instanceof Float32Array)) throw new Error('A joint must be a native vec4');
      return (value[2] * 180) / Math.PI;
    });
    const channels = properties.map(property =>
      Number.parseFloat((root as HTMLElement).style.getPropertyValue(property))
    );
    const rendererInfo = gl.getExtension('WEBGL_debug_renderer_info');
    delete canvas.dataset.e2eCaptureBoundary;
    return {
      scene: root.getAttribute('data-scene') ?? '',
      supportSide: Number.parseFloat(
        (root as HTMLElement).style.getPropertyValue('--rig-body-support-side')
      ),
      channels,
      angles,
      draws: Number(canvas.dataset.e2eNativeDraws ?? 0),
      paintedDraw: Number(canvas.dataset.e2ePaintedDraw),
      width: canvas.width,
      height: canvas.height,
      pixels: Number(canvas.dataset.e2ePainted),
      minX: Number(canvas.dataset.e2eMinX),
      minY: Number(canvas.dataset.e2eMinY),
      maxX: Number(canvas.dataset.e2eMaxX),
      maxY: Number(canvas.dataset.e2eMaxY),
      renderer: String(gl.getParameter(rendererInfo?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER)),
      browser: navigator.userAgent,
      time: Date.now(),
    };
  }, LIMB_PROPERTIES);
}

function checkUploadedPose(
  pose: Awaited<ReturnType<typeof paintedPose>>,
  character: Character,
  variant: Variant
) {
  const joints = limbProfile(character, variant).flatMap(chain => [chain.parent, chain.distal]);
  for (const [index, channel] of LIMB_CHANNELS.entries()) {
    expect(Number.isFinite(pose.channels[index]), channel).toBe(true);
    const joint = joints.find(value => value?.channel === channel);
    if (!joint) {
      expect(pose.channels[index], `${character} must not invent ${channel}`).toBe(0);
      expect(pose.angles[index] ?? 0).toBe(0);
    } else {
      const expected = Math.max(-joint.limit, Math.min(joint.limit, pose.channels[index]));
      // CSS rounds to 0.01 degrees, whereas WebGL receives the continuous value.
      expect(pose.angles[index], `${channel} must reach the real shader`).toBeCloseTo(expected, 1);
      expect(Math.abs(pose.angles[index] ?? Infinity)).toBeLessThanOrEqual(joint.limit + 0.0001);
    }
  }
  expect(pose.draws).toBeGreaterThan(0);
  expect(pose.paintedDraw, 'Pixels and shader angles must describe the same draw').toBe(pose.draws);
  expect(pose.pixels, 'The actual GPU must paint visible source pixels').toBeGreaterThan(0);
  expect(pose.minX, 'Visible pixels must stay clear of the left canvas edge').toBeGreaterThan(0);
  expect(pose.minY, 'Visible pixels must stay clear of the bottom canvas edge').toBeGreaterThan(0);
  expect(pose.maxX, 'Visible pixels must stay clear of the right canvas edge').toBeLessThan(
    pose.width - 1
  );
  expect(pose.maxY, 'Visible pixels must stay clear of the top canvas edge').toBeLessThan(
    pose.height - 1
  );
}

async function requestRasterProbe(face: Locator) {
  await face.locator('[data-volume-canvas]').evaluate(canvas => {
    (canvas as HTMLCanvasElement).dataset.e2eCaptureBoundary = 'true';
  });
}

/** Retain the final actual draw, even when invalidation stops before the interval ends. */
async function advancePose(page: Page, face: Locator, durationMs: number) {
  await requestRasterProbe(face);
  await page.clock.runFor(durationMs + 16);
  return paintedPose(face);
}

function spread(values: number[]): number {
  return Math.max(...values) - Math.min(...values);
}

/** Natural playful mimics lift one foot after shifting weight to the planted one. */
async function observeRestingFeet(
  page: Page,
  face: Locator,
  samples: Awaited<ReturnType<typeof paintedPose>>[]
) {
  const resting: Awaited<ReturnType<typeof paintedPose>>[] = [];
  const left = LIMB_CHANNELS.indexOf('footL');
  const right = LIMB_CHANNELS.indexOf('footR');
  const observed = new Set<number>();
  for (let step = 0; step < 450 && observed.size < 2; step++) {
    const sample = await advancePose(page, face, 250);
    samples.push(sample);
    if (sample.scene || Math.abs(sample.supportSide) < 0.5) continue;
    const l = Math.abs(sample.angles[left] ?? 0);
    const r = Math.abs(sample.angles[right] ?? 0);
    if (Math.max(l, r) <= 0.5 || Math.min(l, r) >= 0.05) continue;
    resting.push(sample);
    observed.add(l > r ? left : right);
  }
  return resting;
}

async function capture(face: Locator, testInfo: TestInfo, name: string): Promise<Buffer> {
  const path = testInfo.outputPath(`${name}.png`);
  const body = await face.locator('[data-volume-canvas]').screenshot({ path });
  await testInfo.attach(name, { path, contentType: 'image/png' });
  return body;
}

for (const character of [...CHARACTERS, 'orbit'] as const) {
  for (const variant of ['female', 'male'] as const) {
    test(`${character} ${variant} paints its supported limbs on the native GPU`, async ({
      page,
      authenticate,
      mockApi,
      baseURL,
    }, testInfo) => {
      test.setTimeout(180_000);
      await authenticate();
      await mockApi(companionRoutes());
      await prepare(page, baseURL, character, variant);
      const face = await openCompanion(page, character, variant);
      const before = await capture(face, testInfo, 'rest-start');
      const samples = [await paintedPose(face)];
      for (let sample = 0; sample < 8; sample++) {
        samples.push(await advancePose(page, face, 400));
      }
      const hasFeet = ['moss', 'lumen', 'bip', 'boulon', 'oscar'].includes(character);
      if (hasFeet) {
        const quiet = samples.filter(
          sample => !sample.scene && Math.abs(sample.supportSide) < 0.01
        );
        expect(
          quiet.length,
          'The neutral stance must include quiet centered support'
        ).toBeGreaterThanOrEqual(2);
        for (const sample of quiet) {
          for (const channel of ['legL', 'legR', 'footL', 'footR'] as const) {
            expect(
              Math.abs(sample.angles[LIMB_CHANNELS.indexOf(channel)] ?? 0),
              `${channel} keeps the quiet stance planted`
            ).toBeLessThan(0.02);
          }
        }
      }
      const viewport = page.viewportSize();
      if (!viewport) throw new Error('The actual app viewport is required');
      // The initial pointer was top-left; cover the remaining turn extremes too.
      for (const [x, y] of [
        [viewport.width - 1, 0],
        [viewport.width - 1, viewport.height - 1],
        [0, viewport.height - 1],
      ]) {
        await page.mouse.move(x, y);
        samples.push(await advancePose(page, face, 640));
      }
      const restingFeet = hasFeet ? await observeRestingFeet(page, face, samples) : [];
      const path = testInfo.outputPath('native-joint-samples.json');
      await writeFile(
        path,
        JSON.stringify(
          { character, variant, channels: LIMB_CHANNELS, samples, restingFeet },
          null,
          2
        )
      );
      await testInfo.attach('native-joint-samples', { path, contentType: 'application/json' });
      if (hasFeet) {
        for (const channel of ['footL', 'footR'] as const) {
          expect(
            restingFeet.some(
              sample => Math.abs(sample.angles[LIMB_CHANNELS.indexOf(channel)] ?? 0) > 0.5
            ),
            `${channel} must move in a naturally scheduled free-foot performance`
          ).toBe(true);
        }
      }
      for (const sample of samples) checkUploadedPose(sample, character, variant);
      if (character !== 'orbit') {
        // Separate shader joints prove this is not merely a head/root sway.
        const moving: LimbChannel[] = ['armL', 'armR'];
        if (hasFeet) {
          moving.push('footL', 'footR');
        }
        if (['bip', 'boulon', 'oscar'].includes(character)) {
          moving.push('wristL', 'wristR', 'legL', 'legR');
        }
        for (const channel of moving) {
          const index = LIMB_CHANNELS.indexOf(channel);
          expect(spread(samples.map(sample => sample.angles[index] ?? 0)), channel).toBeGreaterThan(
            0.05
          );
        }
        expect(samples.at(-1)!.draws).toBeGreaterThan(samples[0].draws);
        const after = await capture(face, testInfo, 'rest-later');
        expect(after.equals(before), 'The actual native canvas must repaint').toBe(false);
      }
    });
  }
}

test('native limbs follow typing, freeze in reduced motion and recover with the source art intact', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}, testInfo) => {
  await authenticate();
  await mockApi(companionRoutes());
  await prepare(page, baseURL, 'bip', 'female');
  const face = await openCompanion(page, 'bip', 'female');
  await expect(face).toHaveAttribute('data-expression', 'neutral');
  const neutral = await paintedPose(face);
  const input = page.getByRole('textbox').first();
  await input.fill('Please consider this question.');
  const attentive = await advancePose(page, face, 640);
  await expect(face).toHaveAttribute('data-expression', 'attentive');
  checkUploadedPose(attentive, 'bip', 'female');
  expect(attentive.angles[0]! - neutral.angles[0]!).toBeGreaterThan(2);
  expect(attentive.angles[1]! - neutral.angles[1]!).toBeLessThan(-2);

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(face).toHaveAttribute('data-volume-ready', 'false');
  // The native media event stops the renderer before queuing the CSS update.
  // Advance the paused frame clock only after that event has been observed.
  await page.clock.runFor(64);
  const frozen = await face.evaluate(
    (root, properties) => ({
      channels: properties.map(property => (root as HTMLElement).style.getPropertyValue(property)),
      draws: root.querySelector<HTMLCanvasElement>('[data-volume-canvas]')?.dataset.e2eNativeDraws,
    }),
    LIMB_PROPERTIES
  );
  expect(frozen.channels).toEqual(LIMB_CHANNELS.map(() => '0deg'));
  await page.clock.runFor(2400);
  expect(
    await face.evaluate(
      (root, properties) => ({
        channels: properties.map(property =>
          (root as HTMLElement).style.getPropertyValue(property)
        ),
        draws:
          root.querySelector<HTMLCanvasElement>('[data-volume-canvas]')?.dataset.e2eNativeDraws,
      }),
      LIMB_PROPERTIES
    )
  ).toEqual(frozen);
  await expectSourceFallback(face);

  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const resumed = await advancePose(page, face, 640);
  await expect(face).toHaveAttribute('data-volume-ready', 'true');
  checkUploadedPose(resumed, 'bip', 'female');
  await capture(face, testInfo, 'resumed');

  // Exercise an actual WebGL loss; the image remains readable without the GPU.
  await face.locator('[data-volume-canvas]').evaluate(canvas => {
    const gl = (canvas as HTMLCanvasElement).getContext('webgl');
    const extension = gl?.getExtension('WEBGL_lose_context');
    if (!extension) throw new Error('The test browser must support native context loss');
    canvas.addEventListener('e2e-restore-context', () => extension.restoreContext(), {
      once: true,
    });
    extension.loseContext();
  });
  await expect(face).toHaveAttribute('data-volume-ready', 'false');
  await expect(face).toBeVisible();
  await expectSourceFallback(face);
  await face.locator('[data-volume-canvas]').dispatchEvent('e2e-restore-context');
  await expect
    .poll(async () => {
      await page.clock.runFor(64);
      return face.getAttribute('data-volume-ready');
    })
    .toBe('true');
  checkUploadedPose(await advancePose(page, face, 0), 'bip', 'female');
});

test('a historical portrait never acquires limb playback while the live companion moves', async ({
  page,
  authenticate,
  mockApi,
  baseURL,
}) => {
  await authenticate();
  await mockApi([
    ...companionRoutes(),
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [
          {
            id: 'limb-latest',
            role: 'assistant',
            content: '<p>The latest answer.</p>',
            created_at: '2026-11-07T11:00:00Z',
            message_metadata: { psyche_state: SAVED_PSYCHE },
          },
          {
            id: 'limb-history',
            role: 'assistant',
            content: '<p>An older answer.</p>',
            created_at: '2026-11-07T10:00:00Z',
            message_metadata: { psyche_state: SAVED_PSYCHE },
          },
        ],
        conversation_id: '00000000-0000-4000-8000-00000000c0h1',
        total_count: 2,
        has_more: false,
        next_cursor: null,
      },
    },
  ]);
  await prepare(page, baseURL, 'bip', 'male');
  const face = await openCompanion(page, 'bip', 'male');
  const history = page.locator('[data-message-id="limb-history"] [data-companion-portrait]');
  await expect(history).toBeVisible();
  await expect(history.locator('canvas')).toHaveCount(0);
  await expect(history.locator('.lia-eyes')).toHaveAttribute('data-motion', 'off');
  const historicalChannels = () =>
    history
      .locator('.lia-eyes')
      .evaluate(
        (root, properties) =>
          properties.map(property => (root as HTMLElement).style.getPropertyValue(property)),
        LIMB_PROPERTIES
      );
  expect(await historicalChannels()).toEqual(LIMB_CHANNELS.map(() => '0deg'));
  const before = await history.screenshot();
  const live = await paintedPose(face);
  await page.clock.runFor(2400);
  await expect(history.locator('canvas')).toHaveCount(0);
  expect(await historicalChannels()).toEqual(LIMB_CHANNELS.map(() => '0deg'));
  expect((await history.screenshot()).equals(before)).toBe(true);
  expect((await paintedPose(face)).draws).toBeGreaterThan(live.draws);
});

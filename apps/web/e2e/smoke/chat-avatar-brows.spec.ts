/**
 * A brow is never drawn on the eye under it (owner rule, 2026-11-12).
 *
 * The oracle is the PAINT, not a formula: a sculpted eye is a texture with a
 * transparent margin, cut by its lids and by the body's own silhouette, and a
 * computation on its square box reads a brow floating above the visible eye as
 * one lying on it. The same frozen frame is therefore photographed twice — the
 * eyes alone, then the brows alone, each as a white silhouette on black — and
 * the two pictures are intersected pixel by pixel.
 *
 * The faces come from the real chat: an answer whose declared register lowers
 * the lids or the brows (ADR-253), at full intensity.
 */
import { test, expect, chatRoutes, waitForClockedHydration } from '../fixtures';
import { BROWS_ALONE, EYES_ALONE, frameFace, shootAlone } from '../fixtures/organ-paint';
import type { Locator, Page } from '@playwright/test';

/** Registers whose face brings a brow down towards the eye, and that face. */
const LOWERED = [
  ['warm', 'tender'],
  ['apologetic', 'sad'],
  ['questioning', 'question'],
  ['careful', 'thinking'],
  ['assured', 'focused'],
  ['weary', 'tired'],
  ['concerned', 'worried'],
] as const;

/**
 * Device pixels per CSS pixel ASKED of the photographs. Engines place the same
 * brow within a third of a CSS pixel of each other (measured: 0.021em under
 * Firefox where Chromium draws 0.026em of skin), and each silhouette loses
 * half a row to its own edge, so a finer picture is a surer one — but an
 * engine may ignore the request (Firefox photographs at one), and every
 * reading below is therefore in CSS pixels, from the density the picture has.
 */
const DENSITY = 4;
/** The line of skin a brow keeps, in CSS pixels at the largest size. */
const SKIN = 1;

/** One eye and its brow, in CSS pixels whatever the density of the picture. */
interface SideReading {
  /** Area the brow paints. */
  brow: number;
  /** Area the eye paints. */
  eye: number;
  /** Area both paint. */
  shared: number;
  /** Rows of nothing between the brow's underside and the eye's top, in the
   * column where they are closest; negative when the brow is below that top. */
  gap: number | null;
}

/** Intersect the two silhouettes, eye by eye. */
async function readBrowsAgainstEyes(page: Page, face: Locator): Promise<SideReading[]> {
  const { clip, middle } = await frameFace(face);
  const eyes = await shootAlone(page, EYES_ALONE, clip);
  const brows = await shootAlone(page, BROWS_ALONE, clip);
  return page.evaluate(
    async ({ eyes, brows, middle, cssWidth }) => {
      const ink = async (encoded: string) => {
        const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = document.createElement('canvas');
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('No 2D context to read the picture with');
        context.drawImage(bitmap, 0, 0);
        const { data, width, height } = context.getImageData(0, 0, bitmap.width, bitmap.height);
        return { width, height, lit: (x: number, y: number) => data[(y * width + x) * 4] >= 128 };
      };
      const eye = await ink(eyes);
      const brow = await ink(brows);
      // What the engine actually photographed at, not what was asked of it.
      const density = eye.width / cssWidth;
      const split = Math.round(middle * eye.width);
      return [
        [0, split],
        [split, eye.width],
      ].map(([from, to]) => {
        const reading = { brow: 0, eye: 0, shared: 0, gap: null as number | null };
        for (let x = from; x < to; x++) {
          let eyeTop = -1;
          let browBottom = -1;
          for (let y = 0; y < eye.height; y++) {
            const onEye = eye.lit(x, y);
            const onBrow = brow.lit(x, y);
            if (onEye) reading.eye += 1;
            if (onBrow) reading.brow += 1;
            if (onEye && onBrow) reading.shared += 1;
            if (onEye && eyeTop < 0) eyeTop = y;
            if (onBrow) browBottom = y;
          }
          if (eyeTop < 0 || browBottom < 0) continue;
          const gap = eyeTop - browBottom - 1;
          reading.gap = reading.gap === null ? gap : Math.min(reading.gap, gap);
        }
        return {
          brow: reading.brow / density ** 2,
          eye: reading.eye / density ** 2,
          shared: reading.shared / density ** 2,
          gap: reading.gap === null ? null : reading.gap / density,
        };
      });
    },
    { eyes, brows, middle, cssWidth: clip.width }
  );
}

/** The most skin a lowered face leaves between its LOWER brow and the eye,
 * in CSS pixels (0.078em at the size photographed here). */
const LOWERED_BROW_REACH = 5;

/** A brow that stopped following the lid would satisfy everything above from
 * a distance: on a face that lowers a lid, a brow still comes DOWN with it.
 * The lower of the two, because a question raises the other on purpose. */
function expectABrowDownWithItsLid(sides: SideReading[], when: string): void {
  const gaps = sides.map(side => side.gap ?? Number.POSITIVE_INFINITY);
  expect(Math.min(...gaps), `no brow came down with the lid (${when})`).toBeLessThanOrEqual(
    LOWERED_BROW_REACH
  );
}

/** A smaller area than this, in CSS pixels, is not an eye, or not a brow, at
 * the size photographed here: a texture that has not arrived, an organ a
 * selector no longer finds. */
const PAINTED_EYE = 50;
const PAINTED_BROW = 12;
/** The most frames, 100 ms apart, a delivery's blink may keep an eye closed. */
const BLINK_FRAMES = 3;

/** A photograph of nothing proves nothing: both organs are on the picture,
 * and then the brow keeps off the eye, with a line of skin between them. */
function expectBrowsOffTheEyes(sides: SideReading[], when: string): void {
  for (const [index, side] of sides.entries()) {
    const which = `${index === 0 ? 'left' : 'right'} eye, ${when}`;
    expect(side.eye, `an eye is painted (${which})`).toBeGreaterThan(PAINTED_EYE);
    expect(side.brow, `a brow is painted (${which})`).toBeGreaterThan(PAINTED_BROW);
    expect(side.shared, `the brow is drawn on the eye (${which})`).toBe(0);
    expect(side.gap, `the brow touches the eye (${which})`).toBeGreaterThanOrEqual(SKIN);
  }
}

async function openCompanion(
  page: Page,
  baseURL: string | undefined,
  character: string,
  variant: 'male' | 'female',
  registers: readonly string[]
): Promise<Locator> {
  if (!baseURL) throw new Error('The hermetic app origin is required');
  await page.context().addCookies([{ name: 'lia_gender', value: variant, url: baseURL }]);
  await page.addInitScript(style => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: true, style, size: 'xl' }, version: 0 })
    );
  }, character);
  let turn = 0;
  await page.route('**/api/v1/agents/chat/stream', async route => {
    const register = registers[turn++ % registers.length];
    const chunks = [
      { type: 'token', content: `Réponse ${register}.`, metadata: null },
      {
        type: 'done',
        content: '',
        metadata: { expressivity: { register, intensity: 1, accent: 'none' } },
      },
    ];
    await route.fulfill({
      contentType: 'text/event-stream',
      body: chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join(''),
    });
  });
  const start = new Date('2026-09-21T12:00:00Z');
  await page.clock.install({ time: start });
  // Paused before navigation: the two photographs of a face are one frame.
  await page.clock.pauseAt(new Date(start.getTime() + 1000));
  await page.goto('/en/dashboard/chat');
  const face = page.locator(
    `.lia-eyes-widget [data-character="${character}"][data-spirit-companion="${variant}"] .lia-eyes`
  );
  await waitForClockedHydration(page, face);
  await expect(face).toBeVisible();
  // A sculpted face is three pictures (the body's silhouette, an eye, its
  // sclera): until they have arrived there is nothing to photograph.
  await expect
    .poll(
      async () => {
        await page.clock.runFor(64);
        const sides = await readBrowsAgainstEyes(page, face);
        return sides.every(side => side.eye > PAINTED_EYE && side.brow > PAINTED_BROW);
      },
      { timeout: 60_000 }
    )
    .toBe(true);
  return face;
}

/** One whole turn, answered in `register`; resolves on the face it earns. */
async function answerIn(
  page: Page,
  face: Locator,
  register: string,
  expression: string
): Promise<void> {
  await page.locator('textarea').fill(`Une question (${register})`);
  await page.locator('textarea').press('Enter');
  await expect
    .poll(
      async () => {
        await page.clock.runFor(32);
        return (
          (await page.getByText(`Réponse ${register}.`, { exact: true }).isVisible()) &&
          (await face.getAttribute('data-expression')) === expression
        );
      },
      { timeout: 30_000 }
    )
    .toBe(true);
}

for (const [character, variant] of [
  ['boulon', 'male'],
  ['oscar', 'female'],
] as const) {
  test.describe(`${character} (${variant})`, () => {
    test.use({ contextOptions: { reducedMotion: 'reduce' }, deviceScaleFactor: DENSITY });

    test('keeps each brow off its eye on every face that lowers a lid or a brow', async ({
      page,
      authenticate,
      mockApi,
      baseURL,
    }) => {
      test.slow();
      await authenticate();
      await mockApi(chatRoutes([]));
      const face = await openCompanion(
        page,
        baseURL,
        character,
        variant,
        LOWERED.map(([register]) => register)
      );
      expectBrowsOffTheEyes(await readBrowsAgainstEyes(page, face), 'at rest');
      for (const [register, expression] of LOWERED) {
        await answerIn(page, face, register, expression);
        // The pose under reduced motion is the settled one, at once.
        await page.clock.runFor(200);
        const sides = await readBrowsAgainstEyes(page, face);
        expectBrowsOffTheEyes(sides, expression);
        expectABrowDownWithItsLid(sides, expression);
      }
    });
  });
}

test.describe('boulon in motion', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' }, deviceScaleFactor: DENSITY });

  test('keeps its brows off its eyes all the way into a question, overshoot included', async ({
    page,
    authenticate,
    mockApi,
    baseURL,
  }) => {
    test.slow();
    await authenticate();
    await mockApi(chatRoutes([]));
    const face = await openCompanion(page, baseURL, 'boulon', 'male', ['questioning']);
    await answerIn(page, face, 'questioning', 'question');
    // The arrival: a counter-move, the tilt, a brow that flies past its pose
    // and comes back — then the delivery's « voilà », which returns to the
    // person on a blink (ADR-294, follow-up of 2026-11-13). Every frame of it
    // is a frame somebody sees: an open eye is measured whole, and what a lid
    // on its way down leaves of the eye still shares no pixel with the brow.
    let closedFrames = 0;
    for (let elapsed = 0; elapsed <= 1600; elapsed += 100) {
      const when = `${elapsed} ms in`;
      const sides = await readBrowsAgainstEyes(page, face);
      if (sides.every(side => side.eye > PAINTED_EYE)) {
        expectBrowsOffTheEyes(sides, when);
      } else {
        closedFrames += 1;
        for (const side of sides) {
          expect(side.brow, `a brow is painted (${when})`).toBeGreaterThan(PAINTED_BROW);
          expect(side.shared, `the brow is drawn on a closing eye (${when})`).toBe(0);
        }
      }
      await page.clock.runFor(100);
    }
    // A blink is a few frames. Eyes unpainted for longer would mean nothing was
    // measured: a photograph of nothing proves nothing.
    expect(closedFrames, 'frames the blink keeps an eye closed').toBeLessThanOrEqual(BLINK_FRAMES);
  });
});

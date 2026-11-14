/**
 * The companion's organs as the browser PAINTS them — not as a formula reads them.
 *
 * A sculpted eye is a texture with a transparent margin, cut by its lids and by the
 * body's own silhouette: a computation on its square box sees an eye where nothing is
 * painted, and a channel can move while not one pixel does (measured 2026-11-12: a wind
 * squint at 0.86 of the eye's height lost no pixel of a sculpted eye). These helpers
 * photograph ONE kind of organ of the floating companion alone, white on black, for a
 * spec to read back in CSS pixels.
 */
import type { Locator, Page } from '@playwright/test';

/** Everything off the page but one organ of the floating companion. */
const ALONE =
  'html,body{background:#000!important}*,*::before,*::after{visibility:hidden!important}' +
  '.lia-eyes-widget .lia-eye{filter:none!important}';

export const EYES_ALONE =
  ALONE +
  '.lia-eyes-widget .lia-eye-blink,.lia-eyes-widget .lia-eye-blink *{visibility:visible!important}' +
  '.lia-eyes-widget .lia-eye-blink{filter:brightness(0) invert(1)!important}';

export const BROWS_ALONE =
  ALONE +
  '.lia-eyes-widget .lia-eye-brow,.lia-eyes-widget .lia-eye-brow *{visibility:visible!important}' +
  '.lia-eyes-widget .lia-eye-brow{filter:brightness(0) invert(1)!important}' +
  '.lia-eyes-widget .lia-eye-brow path{filter:none!important}';

export const MOUTH_ALONE =
  ALONE +
  '.lia-eyes-widget .lia-mouth,.lia-eyes-widget .lia-mouth *{visibility:visible!important}' +
  '.lia-eyes-widget .lia-mouth{filter:brightness(0) invert(1)!important}';

/** What a weather scene carries, alone and without the shadow its artwork casts. */
function sceneProp(kind: 'drop' | 'flake'): string {
  const slot = `.lia-eyes-widget .lia-ambient-weather--${kind}`;
  return (
    ALONE +
    `${slot},${slot} *{visibility:visible!important}` +
    `${slot}{filter:brightness(0) invert(1)!important}` +
    `${slot} .lia-ambient-scene-${kind}{filter:none!important}`
  );
}

export const DROP_ALONE = sceneProp('drop');
export const FLAKE_ALONE = sceneProp('flake');

/** The companion's head as painted — its body, face and organs — with no weather on it. */
export const HEAD_ALONE =
  ALONE +
  '.lia-eyes-widget .lia-eyes,.lia-eyes-widget .lia-eyes *,' +
  '.lia-eyes-widget .lia-eyes *::before,.lia-eyes-widget .lia-eyes *::after' +
  '{visibility:visible!important}' +
  '.lia-eyes-widget .lia-ambient-weather,.lia-eyes-widget .lia-ambient-weather *,' +
  '.lia-eyes-widget .lia-ambient-weather *::before,.lia-eyes-widget .lia-ambient-weather *::after,' +
  '.lia-eyes-widget .lia-head-shadow,.lia-eyes-widget .lia-emote{visibility:hidden!important}' +
  '.lia-eyes-widget .lia-eyes{filter:brightness(0) invert(1)!important}';

const CROWN = '.lia-eyes-widget .lia-ambient-weather--freezing:not(.lia-ambient-breath)';

/** The frost crown alone, without the drop shadow its artwork casts. */
export const CROWN_ALONE =
  ALONE +
  `${CROWN},${CROWN} *{visibility:visible!important}` +
  `${CROWN}{filter:brightness(0) invert(1)!important}` +
  `${CROWN} .lia-ambient-prop{filter:none!important}`;

export interface Clip {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Where the face is on the page, and where its two eyes part (a share of its width). */
export interface FaceFrame {
  clip: Clip;
  middle: number;
}

export async function frameFace(face: Locator): Promise<FaceFrame> {
  const frame = await face.evaluate(root => {
    const box = root.getBoundingClientRect();
    const centres = [...root.querySelectorAll('.lia-eye-blink')].map(eye => {
      const rect = eye.getBoundingClientRect();
      return rect.left + rect.width / 2;
    });
    return { x: box.x, y: box.y, width: box.width, height: box.height, centres };
  });
  if (frame.centres.length !== 2) throw new Error('The face must draw two eyes');
  return {
    clip: { x: frame.x, y: frame.y, width: frame.width, height: frame.height },
    middle: ((frame.centres[0] + frame.centres[1]) / 2 - frame.x) / frame.width,
  };
}

/** One organ alone, as the browser paints it (a PNG, in base64). A constructed sheet,
 * because the application's content policy has no say over a sheet a script builds. */
export async function shootAlone(page: Page, css: string, clip: Clip): Promise<string> {
  await page.evaluate(text => {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(text);
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
  }, css);
  const shot = await page.screenshot({ clip });
  await page.evaluate(() => {
    document.adoptedStyleSheets = document.adoptedStyleSheets.slice(0, -1);
  });
  return shot.toString('base64');
}

/**
 * One element alone, taken again while the picture has nothing painted: Firefox can
 * hand back the first picture of a freshly filtered layer before its artwork is
 * decoded (measured 2026-11-13: the frost crown alone, all black, once in three).
 * What is never painted stays empty after the last attempt, for its test to say so.
 */
export async function shootPainted(page: Page, css: string, clip: Clip): Promise<string> {
  let shot = '';
  for (let attempt = 0; attempt < 8; attempt++) {
    shot = await shootAlone(page, css, clip);
    const painted = await page.evaluate(async encoded => {
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No 2D context to read the picture with');
      context.drawImage(bitmap, 0, 0);
      const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
      for (let i = 0; i < data.length; i += 4) if (data[i] >= 128) return true;
      return false;
    }, shot);
    if (painted) break;
    await page.waitForTimeout(120);
  }
  return shot;
}

/**
 * How tall each eye is painted, in CSS pixels: its tallest painted column, left then
 * right. Read from the density the picture HAS — an engine may ignore the one asked.
 */
export async function paintedEyeHeights(page: Page, face: Locator): Promise<[number, number]> {
  const { clip, middle } = await frameFace(face);
  const eyes = await shootAlone(page, EYES_ALONE, clip);
  return page.evaluate(
    async ({ encoded, middle, cssWidth }) => {
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No 2D context to read the picture with');
      context.drawImage(bitmap, 0, 0);
      const { data, width, height } = context.getImageData(0, 0, bitmap.width, bitmap.height);
      const density = width / cssWidth;
      const tallest = (from: number, to: number) => {
        let best = 0;
        for (let x = from; x < to; x++) {
          let painted = 0;
          for (let y = 0; y < height; y++) if (data[(y * width + x) * 4] >= 128) painted += 1;
          best = Math.max(best, painted);
        }
        return best / density;
      };
      const split = Math.round(middle * width);
      return [tallest(0, split), tallest(split, width)] as [number, number];
    },
    { encoded: eyes, middle, cssWidth: clip.width }
  );
}

/**
 * Where the two eyes are painted, top to bottom: the mean row of every painted pixel,
 * in CSS pixels from the face's top. A look down moves it down, wherever the formula
 * says the gaze points.
 */
export async function paintedEyesRow(page: Page, face: Locator): Promise<number> {
  const { clip } = await frameFace(face);
  const eyes = await shootAlone(page, EYES_ALONE, clip);
  return page.evaluate(
    async ({ encoded, cssWidth }) => {
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No 2D context to read the picture with');
      context.drawImage(bitmap, 0, 0);
      const { data, width, height } = context.getImageData(0, 0, bitmap.width, bitmap.height);
      let rows = 0;
      let painted = 0;
      for (let y = 0; y < height; y++)
        for (let x = 0; x < width; x++)
          if (data[(y * width + x) * 4] >= 128) {
            rows += y;
            painted += 1;
          }
      if (painted === 0) throw new Error('No eye is painted');
      return rows / painted / (width / cssWidth);
    },
    { encoded: eyes, cssWidth: clip.width }
  );
}

/**
 * How tall the mouth is painted, in CSS pixels: its tallest painted column, 0 for a
 * mouth shut to nothing. A mouth that opens on a voice must open on the picture too,
 * whatever its channel says. Framed on the mouth's own box, widely: a face's box need
 * not hold its mouth, and a mouth opens beyond its resting box.
 */
export async function paintedMouthHeight(page: Page, face: Locator): Promise<number> {
  const clip = await face.locator('.lia-mouth').evaluate(mouth => {
    const box = mouth.getBoundingClientRect();
    const reach = Math.max(box.width, box.height);
    return {
      x: box.x - reach,
      y: box.y - reach,
      width: box.width + 2 * reach,
      height: box.height + 2 * reach,
    };
  });
  const mouth = await shootAlone(page, MOUTH_ALONE, clip);
  return page.evaluate(
    async ({ encoded, cssWidth }) => {
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No 2D context to read the picture with');
      context.drawImage(bitmap, 0, 0);
      const { data, width, height } = context.getImageData(0, 0, bitmap.width, bitmap.height);
      let tallest = 0;
      for (let x = 0; x < width; x++) {
        let painted = 0;
        for (let y = 0; y < height; y++) if (data[(y * width + x) * 4] >= 128) painted += 1;
        tallest = Math.max(tallest, painted);
      }
      return tallest / (width / cssWidth);
    },
    { encoded: mouth, cssWidth: clip.width }
  );
}

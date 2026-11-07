/**
 * What a phone screen is held to (owner, 2026-11-06): a row of controls stands on one line, and
 * what starts a line starts at the edge of what stands under it. Real boxes, never class names.
 */
import type { Locator, Page } from '@playwright/test';

import { expect } from '../fixtures';

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A pixel of slack: boxes are read at sub-pixel positions. */
const SLACK = 1;
/** Two controls whose middles round to one step stand on one line. */
const LINE_STEP = 24;

export async function boxOf(target: Locator): Promise<Box> {
  const box = await target.boundingBox();
  if (box === null) throw new Error('not drawn');
  return box;
}

/** What iOS zooms into, and stays zoomed on, under this size. */
const FIELD_MIN_PX = 16;

/** Every field a thumb can reach is large enough for the page to stay whole under the keyboard. */
export async function expectNoZoomOnFocus(page: Page): Promise<void> {
  const small = await page.evaluate(min => {
    const fields = document.querySelectorAll<HTMLElement>(
      'input:not([type=checkbox],[type=radio],[type=range],[type=color],[type=file],[type=hidden]),textarea,select,[contenteditable=true]'
    );
    return [...fields]
      .filter(field => field.offsetParent !== null && parseFloat(getComputedStyle(field).fontSize) < min)
      .map(field => `${field.tagName} ${field.getAttribute('aria-label') ?? field.id}`);
  }, FIELD_MIN_PX);
  expect(small, 'fields iOS would zoom into').toEqual([]);
}

/** Every control stands on one line, whatever their heights. */
export async function expectOnOneLine(...controls: readonly Locator[]): Promise<void> {
  const boxes = await Promise.all(controls.map(boxOf));
  const middles = boxes.map(box => box.y + box.height / 2);
  expect(Math.max(...middles) - Math.min(...middles), 'one line').toBeLessThanOrEqual(SLACK);
  for (let index = 1; index < boxes.length; index += 1) {
    const before = boxes[index - 1];
    const box = boxes[index];
    if (!before || !box) continue;
    expect(box.x, 'in reading order, side by side').toBeGreaterThanOrEqual(
      before.x + before.width - SLACK
    );
  }
}

/** Each control on a line of its own, the whole width of the first. */
export async function expectStackedWhole(...controls: readonly Locator[]): Promise<void> {
  const boxes = await Promise.all(controls.map(boxOf));
  const [first] = boxes;
  if (!first) throw new Error('nothing to measure');
  boxes.forEach((box, index) => {
    expect(Math.abs(box.x - first.x), 'one left edge').toBeLessThanOrEqual(SLACK);
    expect(Math.abs(box.width - first.width), 'one width').toBeLessThanOrEqual(SLACK);
    const above = boxes[index - 1];
    if (above) expect(box.y, 'under the one before').toBeGreaterThanOrEqual(above.y + above.height);
  });
}

/** Where the words of a control start, its padding aside. */
export async function wordStartOf(target: Locator): Promise<number> {
  return target.evaluate(node => {
    const words = document.createRange();
    words.selectNodeContents(node);
    return words.getBoundingClientRect().x;
  });
}

/** Two controls share their left edge. */
export async function expectSameStart(first: Locator, second: Locator): Promise<void> {
  const [one, other] = await Promise.all([boxOf(first), boxOf(second)]);
  expect(Math.abs(one.x - other.x), 'one left edge').toBeLessThanOrEqual(SLACK);
}

/** The first control ends where the second does. */
export async function expectSameEnd(first: Locator, second: Locator): Promise<void> {
  const [one, other] = await Promise.all([boxOf(first), boxOf(second)]);
  expect(
    Math.abs(one.x + one.width - (other.x + other.width)),
    'one right edge'
  ).toBeLessThanOrEqual(SLACK);
}

/** Two controls share their middle. */
export async function expectSameCentre(first: Locator, second: Locator): Promise<void> {
  const [one, other] = await Promise.all([boxOf(first), boxOf(second)]);
  expect(
    Math.abs(one.x + one.width / 2 - (other.x + other.width / 2)),
    'one middle'
  ).toBeLessThanOrEqual(SLACK);
}

/** Whatever line each control lands on, every line stands in the middle of the panel. */
export async function expectLinesCentredIn(
  panel: Locator,
  ...controls: readonly Locator[]
): Promise<void> {
  const [box, ...boxes] = await Promise.all([panel, ...controls].map(boxOf));
  if (!box) throw new Error('no panel');
  const lines = new Map<number, Box[]>();
  for (const control of boxes) {
    const middle = Math.round((control.y + control.height / 2) / LINE_STEP);
    lines.set(middle, [...(lines.get(middle) ?? []), control]);
  }
  for (const line of lines.values()) {
    const start = Math.min(...line.map(control => control.x));
    const end = Math.max(...line.map(control => control.x + control.width));
    const room = Math.abs(start - box.x - (box.x + box.width - end));
    expect(room, 'as much room on either side').toBeLessThanOrEqual(2 * SLACK);
  }
}

/** The control is drawn whole inside its panel: nothing of it is cut at the edge. */
export async function expectInside(panel: Locator, control: Locator): Promise<void> {
  const [box, inner] = await Promise.all([boxOf(panel), boxOf(control)]);
  expect(inner.x, 'inside on the left').toBeGreaterThanOrEqual(box.x - SLACK);
  expect(inner.x + inner.width, 'inside on the right').toBeLessThanOrEqual(
    box.x + box.width + SLACK
  );
}

/** The second control stands entirely under the first. */
export async function expectUnder(upper: Locator, lower: Locator): Promise<void> {
  const [above, under] = await Promise.all([boxOf(upper), boxOf(lower)]);
  expect(under.y, 'under it').toBeGreaterThanOrEqual(above.y + above.height - SLACK);
}

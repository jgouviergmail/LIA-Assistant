/**
 * Where a directed look lands: the screen DECLARES what can be looked at, and
 * one function turns its real position into a gaze. A direction hard-coded in
 * the engine points at the same place wherever the person parked the face.
 */

import { afterEach, describe, expect, it } from 'vitest';

import {
  GAZE_TARGET_ATTRIBUTE,
  gazeTargetProps,
  gazeToward,
  locateGazeTarget,
} from '../gaze-target';

const VIEWPORT = { width: 1000, height: 800 };

function declare(target: string, rect: DOMRect): HTMLElement {
  const element = document.createElement('div');
  element.setAttribute(GAZE_TARGET_ATTRIBUTE, target);
  element.getBoundingClientRect = () => rect;
  document.body.append(element);
  return element;
}

afterEach(() => document.body.replaceChildren());

describe('the direction of a look', () => {
  it('is the offset from the centre of the face, a half-viewport for a full deflection', () => {
    const face = new DOMRect(400, 300, 200, 200);
    expect(gazeToward(face, { x: 500, y: 400 }, VIEWPORT)).toEqual({ x: 0, y: 0 });
    expect(gazeToward(face, { x: 750, y: 200 }, VIEWPORT)).toEqual({ x: 0.5, y: -0.5 });
  });

  it('never exceeds a full deflection, however far the thing is', () => {
    const face = new DOMRect(0, 0, 100, 100);
    expect(gazeToward(face, { x: 5000, y: -5000 }, VIEWPORT)).toEqual({ x: 1, y: -1 });
  });

  it('changes with the place of the face: the same text is below a docked face and beside a parked one', () => {
    const text = { x: 500, y: 600 };
    const docked = gazeToward(new DOMRect(450, 0, 100, 100), text, VIEWPORT);
    const parked = gazeToward(new DOMRect(880, 550, 100, 100), text, VIEWPORT);
    expect(docked.x).toBe(0);
    expect(docked.y).toBeGreaterThan(0.9);
    expect(parked.x).toBeLessThan(-0.8);
    expect(Math.abs(parked.y)).toBeLessThan(0.05);
  });
});

describe('what the screen declares', () => {
  it('finds the answer being written at the end of its block, where the next words appear', () => {
    declare('answer', new DOMRect(100, 200, 600, 300));
    expect(locateGazeTarget('answer', VIEWPORT)).toEqual({ x: 400, y: 500 });
  });

  it('keeps the point on screen when the block runs past the fold', () => {
    declare('answer', new DOMRect(100, 200, 600, 2000));
    expect(locateGazeTarget('answer', VIEWPORT)).toEqual({ x: 400, y: 800 });
  });

  it('reads the last declaration when a screen holds several', () => {
    declare('answer', new DOMRect(0, 0, 200, 100));
    declare('answer', new DOMRect(100, 200, 600, 300));
    expect(locateGazeTarget('answer', VIEWPORT)).toEqual({ x: 400, y: 500 });
  });

  it('answers nothing when the screen declares nothing, or a block with no box', () => {
    expect(locateGazeTarget('answer', VIEWPORT)).toBeNull();
    declare('answer', new DOMRect(0, 0, 0, 0));
    expect(locateGazeTarget('answer', VIEWPORT)).toBeNull();
  });

  it('is declared by the attribute it is read by', () => {
    for (const target of ['answer', 'input', 'notification'] as const)
      expect(gazeTargetProps(target)).toEqual({ [GAZE_TARGET_ATTRIBUTE]: target });
  });
});

/** A toast as the toaster renders it: the library marks the one in front. */
function toast(rect: DOMRect, front: boolean, removed = false): HTMLElement {
  const element = document.createElement('li');
  element.setAttribute('data-sonner-toast', '');
  element.setAttribute('data-front', String(front));
  if (removed) element.setAttribute('data-removed', 'true');
  element.getBoundingClientRect = () => rect;
  document.body.append(element);
  return element;
}

describe('the field the person types in', () => {
  it('is looked at in its middle, not where the next words of an answer appear', () => {
    declare('input', new DOMRect(100, 600, 600, 80));
    expect(locateGazeTarget('input', VIEWPORT)).toEqual({ x: 400, y: 640 });
  });
});

describe('a notification', () => {
  it('is the toast in front of the toaster, looked at in its middle', () => {
    toast(new DOMRect(350, 32, 300, 60), true);
    toast(new DOMRect(350, 108, 300, 60), false);
    expect(locateGazeTarget('notification', VIEWPORT)).toEqual({ x: 500, y: 62 });
  });

  it('is never a toast on its way out', () => {
    toast(new DOMRect(350, 32, 300, 60), true, true);
    expect(locateGazeTarget('notification', VIEWPORT)).toBeNull();
  });

  it('is where a page with no toast shows it: the place the screen declares', () => {
    declare('notification', new DOMRect(900, 700, 44, 44));
    expect(locateGazeTarget('notification', VIEWPORT)).toEqual({ x: 922, y: 722 });
  });

  it('is the toast that has just appeared rather than a badge that was already there', () => {
    // The toaster is rendered after the page: a toast comes last in the document.
    declare('notification', new DOMRect(900, 700, 44, 44));
    toast(new DOMRect(350, 32, 300, 60), true);
    expect(locateGazeTarget('notification', VIEWPORT)).toEqual({ x: 500, y: 62 });
  });

  it('is never what another target declares', () => {
    declare('input', new DOMRect(100, 600, 600, 80));
    toast(new DOMRect(350, 32, 300, 60), true);
    expect(locateGazeTarget('input', VIEWPORT)).toEqual({ x: 400, y: 640 });
    expect(locateGazeTarget('answer', VIEWPORT)).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';
import { placeSelectionMenu, selectionMenuSpace } from '../selection-position';

const viewport = { top: 0, left: 0, width: 800, height: 600 };

describe('selection menu free space', () => {
  it('uses a side when selected text spans the viewport height', () => {
    const anchor = { top: -20, bottom: 620, left: 400, width: 200 };
    const size = { width: 200, height: 100 };
    const space = selectionMenuSpace(anchor, size, viewport);
    expect(space).not.toBeNull();
    expect(placeSelectionMenu(anchor, size, space!)).toEqual({ left: 192, top: 8 });
  });

  it('limits the menu to a scrollable free strip rather than covering a long passage', () => {
    const anchor = { top: 90, bottom: 510, left: 8, width: 784 };
    const space = selectionMenuSpace(anchor, { width: 720, height: 180 }, viewport);
    expect(space?.height).toBe(74);
    expect(placeSelectionMenu(anchor, { width: 720, height: 74 }, space!)).toEqual({
      left: 8,
      top: 8,
    });
  });

  it('does not display a detached menu when the selection is offscreen', () => {
    expect(
      selectionMenuSpace(
        { top: -100, bottom: -50, left: 40, width: 200 },
        { width: 300, height: 50 },
        viewport
      )
    ).toBeNull();
  });
});

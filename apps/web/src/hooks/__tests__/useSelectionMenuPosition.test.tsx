import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useSelectionMenuPosition } from '../useSelectionMenuPosition';
import type { SelectionRect } from '@/lib/selection-position';

function Menu({ anchorOf, visible = true }: { anchorOf: () => SelectionRect; visible?: boolean }) {
  const ref = useSelectionMenuPosition(anchorOf);
  return visible ? <div ref={ref} data-testid="menu" style={{ position: 'fixed' }} /> : null;
}

/** Browser boundary: WebKit client rectangles move with the visual viewport,
 * while CSS fixed top/left still describe the layout viewport. Other engines
 * keep client rectangles layout-relative even while the keyboard pans.
 */
function geometry(clientOrigin: 'visual' | 'layout', menuHeight = 44) {
  const viewport = Object.assign(new EventTarget(), {
    offsetLeft: 40,
    offsetTop: 180,
    width: 350,
    height: 360,
  });
  vi.stubGlobal('visualViewport', viewport);
  let field = new DOMRect(75, 450, 240, 40);
  const clientRect = (rect: DOMRect) =>
    clientOrigin === 'visual'
      ? new DOMRect(
          rect.left - viewport.offsetLeft,
          rect.top - viewport.offsetTop,
          rect.width,
          rect.height
        )
      : rect;
  const nativeRect = HTMLElement.prototype.getBoundingClientRect;
  const measure = vi
    .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockImplementation(function (this: HTMLElement) {
      if (this.dataset.testid !== 'menu') return nativeRect.call(this);
      return clientRect(
        new DOMRect(
          parseFloat(this.style.left) || 0,
          parseFloat(this.style.top) || 0,
          220,
          menuHeight
        )
      );
    });
  return {
    viewport,
    measure,
    anchorOf: () => clientRect(field),
    moveField: (top: number) => {
      field = new DOMRect(field.left, top, field.width, field.height);
    },
    assertAdjacent: () => {
      const menu = screen.getByTestId('menu');
      const rect = menu.getBoundingClientRect();
      const target = clientRect(field);
      const visibleTop = clientOrigin === 'visual' ? 0 : viewport.offsetTop;
      const visibleLeft = clientOrigin === 'visual' ? 0 : viewport.offsetLeft;
      expect(menu.style.visibility).toBe('visible');
      expect(target.top - rect.bottom).toBe(8);
      expect(rect.left).toBe(target.left);
      expect(rect.top).toBeGreaterThanOrEqual(visibleTop);
      expect(rect.bottom).toBeLessThanOrEqual(visibleTop + viewport.height);
      expect(rect.left).toBeGreaterThanOrEqual(visibleLeft);
      expect(rect.right).toBeLessThanOrEqual(visibleLeft + viewport.width);
    },
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('uses the window bounds without VisualViewport and leaves internal menu scrolling alone', () => {
  const scene = geometry('layout');
  vi.stubGlobal('visualViewport', undefined);
  vi.stubGlobal('ResizeObserver', undefined);
  vi.stubGlobal('innerWidth', 390);
  vi.stubGlobal('innerHeight', 844);
  render(<Menu anchorOf={scene.anchorOf} />);
  scene.assertAdjacent();
  const menu = screen.getByTestId('menu');
  const reads = scene.measure.mock.calls.length;
  act(() => menu.dispatchEvent(new Event('scroll')));
  expect(scene.measure).toHaveBeenCalledTimes(reads);
  scene.moveField(470);
  act(() => window.dispatchEvent(new Event('resize')));
  scene.assertAdjacent();
});

it('attaches no observer or listener for an absent surface', () => {
  const listen = vi.spyOn(window, 'addEventListener');
  const anchorOf = vi.fn(() => new DOMRect(75, 450, 240, 40));
  render(<Menu anchorOf={anchorOf} visible={false} />);
  expect(anchorOf).not.toHaveBeenCalled();
  expect(listen.mock.calls.filter(([event]) => event === 'resize')).toEqual([]);
});

for (const origin of ['visual', 'layout'] as const) {
  it.each([44, 88, 160])(
    `keeps a %ipx caret/menu/answer beside the bottom field with ${origin}-relative client rects`,
    height => {
      const scene = geometry(origin, height);
      render(<Menu anchorOf={scene.anchorOf} />);
      scene.assertAdjacent();
    }
  );

  it(`follows keyboard opening, panning and closing without accumulated drift (${origin})`, () => {
    const scene = geometry(origin);
    Object.assign(scene.viewport, { offsetLeft: 0, offsetTop: 0, height: 800 });
    scene.moveField(680);
    const { unmount } = render(<Menu anchorOf={scene.anchorOf} />);
    scene.assertAdjacent();
    act(() => {
      Object.assign(scene.viewport, { offsetLeft: 40, offsetTop: 180, height: 360 });
      scene.moveField(450);
      scene.viewport.dispatchEvent(new Event('resize'));
    });
    scene.assertAdjacent();
    const menu = screen.getByTestId('menu');
    menu.scrollTop = 32;
    for (let step = 0; step < 5; step++) {
      act(() => {
        scene.viewport.offsetTop = 220;
        scene.viewport.dispatchEvent(new Event('scroll'));
      });
      scene.assertAdjacent();
      expect(menu.scrollTop).toBe(32);
    }
    act(() => {
      Object.assign(scene.viewport, { offsetLeft: 0, offsetTop: 0, height: 800 });
      scene.moveField(680);
      scene.viewport.dispatchEvent(new Event('resize'));
    });
    scene.assertAdjacent();
    unmount();
    const reads = scene.measure.mock.calls.length;
    scene.viewport.dispatchEvent(new Event('scroll'));
    expect(scene.measure).toHaveBeenCalledTimes(reads);
  });

  it(`hides an offscreen anchor and follows its return (${origin})`, () => {
    const scene = geometry(origin);
    scene.moveField(100);
    render(<Menu anchorOf={scene.anchorOf} />);
    expect(screen.getByTestId('menu').style.visibility).toBe('hidden');
    act(() => {
      scene.moveField(450);
      document.dispatchEvent(new Event('scroll'));
    });
    scene.assertAdjacent();
  });
}

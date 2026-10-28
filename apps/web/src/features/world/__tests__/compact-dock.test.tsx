import { act, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { useCompactConversationDock } from '../useCompactConversationDock';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function Dock({ active = true }: { active?: boolean }) {
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  useCompactConversationDock(host, active);
  return (
    <div>
      <div ref={setHost} data-testid="dock" />
    </div>
  );
}

it('limits the compact surface to the scene when the app footer is above the viewport bottom', () => {
  const viewport = Object.assign(new EventTarget(), {
    width: 568,
    height: 320,
    offsetTop: 0,
    offsetLeft: 0,
  });
  vi.stubGlobal('visualViewport', viewport);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    new DOMRect(0, 73, 568, 207)
  );
  render(<Dock />);
  expect(screen.getByTestId('dock').style.getPropertyValue('--world-compact-height')).toBe('87px');
});

it('raises the compact composer above the phone keyboard and releases its geometry', () => {
  const viewport = Object.assign(new EventTarget(), {
    width: 390,
    height: 844,
    offsetTop: 0,
    offsetLeft: 0,
  });
  vi.stubGlobal('visualViewport', viewport);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    new DOMRect(0, 60, 390, 784)
  );
  const view = render(<Dock />);
  const dock = screen.getByTestId('dock');
  expect(dock.style.bottom).toBe('');
  act(() => {
    viewport.height = 320;
    viewport.offsetTop = 40;
    viewport.dispatchEvent(new Event('resize'));
  });
  expect(dock.style.bottom).toBe('492px');
  expect(dock.dataset.keyboard).toBe('true');
  expect(
    Number.parseFloat(dock.style.getPropertyValue('--world-compact-height'))
  ).toBeLessThanOrEqual(284);
  view.rerender(<Dock active={false} />);
  expect(dock.style.bottom).toBe('');
  expect(dock.style.getPropertyValue('--world-compact-height')).toBe('');
  act(() => viewport.dispatchEvent(new Event('resize')));
  expect(dock.style.bottom).toBe('');
});

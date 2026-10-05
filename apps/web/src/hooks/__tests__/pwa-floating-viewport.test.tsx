import { act, cleanup, render, screen } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { useEyesDrag } from '@/components/eyes/useEyesDrag';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';

function Eyes({ visible }: { visible: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useEyesDrag(ref, 'chat', visible);
  return visible ? (
    <div
      ref={ref}
      data-testid="eyes"
      style={drag.displayPos ? { left: drag.displayPos.x, top: drag.displayPos.y } : undefined}
    />
  ) : null;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  useEyesWidgetStore.getState().reset();
});
it('survives the iOS keyboard pan beyond innerHeight while the companion is hidden by Simli', () => {
  vi.stubGlobal('innerHeight', 320);
  vi.stubGlobal(
    'visualViewport',
    Object.assign(new EventTarget(), { width: 390, height: 320, offsetLeft: 0, offsetTop: 350 })
  );
  useEyesWidgetStore.getState().setPosition({ xPct: 20, yPct: 20 });
  expect(() => render(<Eyes visible={false} />)).not.toThrow();
  expect(useEyesWidgetStore.getState().position).toEqual({ xPct: 20, yPct: 20 });
});
it('keeps a visible companion inside the panned viewport then restores the saved spot when the keyboard closes', () => {
  vi.stubGlobal('innerHeight', 320);
  const viewport = Object.assign(new EventTarget(), {
    width: 390,
    height: 320,
    offsetLeft: 0,
    offsetTop: 350,
  });
  vi.stubGlobal('visualViewport', viewport);
  useEyesWidgetStore.getState().setPosition({ xPct: 20, yPct: 20 });
  render(<Eyes visible />);
  expect(screen.getByTestId('eyes').style.top).toBe('350px');
  act(() => {
    viewport.offsetTop = 0;
    viewport.dispatchEvent(new Event('scroll'));
  });
  expect(screen.getByTestId('eyes').style.top).toBe('64px');
  expect(useEyesWidgetStore.getState().position).toEqual({ xPct: 20, yPct: 20 });
});
it('normalizes invalid saved coordinates and leaves equal placements idempotent', () => {
  const store = useEyesWidgetStore.getState();
  store.setPosition({ xPct: 20, yPct: 30 });
  const saved = useEyesWidgetStore.getState();
  store.setPosition({ xPct: 20, yPct: 30 });
  expect(useEyesWidgetStore.getState()).toBe(saved);
  store.setPosition({ xPct: NaN, yPct: Infinity });
  expect(useEyesWidgetStore.getState().position).toBeNull();
});

it('does not rewrite an unchanged landing placement', () => {
  const store = useEyesWidgetStore.getState();
  store.setLandingPosition({ xPct: 20, yPct: 30 });
  const saved = useEyesWidgetStore.getState();
  store.setLandingPosition({ xPct: 20, yPct: 30 });
  expect(useEyesWidgetStore.getState()).toBe(saved);
});

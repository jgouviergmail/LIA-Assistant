import { useLayoutEffect, useRef } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { BodyVolume } from '../volume/BodyVolume';
import type { VolumeCharacter } from '../volume/volume-geometry';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import { activeFrameSubscribers } from '../rig/scheduler';

interface Allocation {
  canvas: HTMLCanvasElement;
  dispose: Mock<() => void>;
}
const binding = vi.hoisted(() => ({
  bind: vi.fn(),
  allocations: [] as Allocation[],
}));
vi.mock('../volume/volume-binding', () => ({ bindBodyVolume: binding.bind }));

interface HarnessProps {
  character?: VolumeCharacter;
  variant?: SpiritVariant;
  size?: EyesSize;
  enabled: boolean;
  onLayout?: (root: HTMLSpanElement) => void;
}
function Harness({
  character = 'oscar',
  variant = 'male',
  size = 'sm',
  enabled,
  onLayout,
}: HarnessProps) {
  const root = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (root.current) onLayout?.(root.current);
  });
  return (
    <span ref={root} className="lia-eyes" data-volume-ready="false">
      <BodyVolume character={character} variant={variant} size={size} enabled={enabled} />
    </span>
  );
}

beforeEach(() => {
  binding.bind.mockReset();
  binding.allocations.length = 0;
  binding.bind.mockImplementation((canvas: HTMLCanvasElement, root: HTMLElement) => {
    // This port stands for a successful native draw, not an independent clock.
    canvas.dataset.painted = 'true';
    root.dataset.volumeReady = 'true';
    const dispose = vi.fn(() => {
      root.dataset.volumeReady = 'false';
    });
    binding.allocations.push({ canvas, dispose });
    return dispose;
  });
  vi.stubGlobal('devicePixelRatio', 2);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('native body volume lifetime', () => {
  it('does not mount a canvas or bind graphics when locally stopped', () => {
    const { container } = render(<Harness enabled={false} />);
    expect(container.querySelector('canvas')).toBeNull();
    expect(binding.bind).not.toHaveBeenCalled();
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('binds the current identity once and releases old bounded buffers on resize, gender change and pause', () => {
    const view = render(<Harness enabled />);
    const first = binding.allocations[0];
    expect(first.canvas).toHaveAttribute('aria-hidden', 'true');
    expect(first.canvas).toHaveAttribute('data-volume-canvas');
    expect(binding.bind).toHaveBeenLastCalledWith(
      first.canvas,
      first.canvas.closest('.lia-eyes'),
      'oscar',
      'male'
    );
    view.rerender(<Harness enabled size="xl" variant="female" />);
    const latest = binding.allocations[1];
    expect(first.dispose).toHaveBeenCalledOnce();
    expect(latest.canvas).not.toBe(first.canvas);
    expect(latest.canvas.width).toBe(192);
    expect(latest.canvas.height).toBe(192);
    expect(binding.bind).toHaveBeenLastCalledWith(
      latest.canvas,
      latest.canvas.closest('.lia-eyes'),
      'oscar',
      'female'
    );
    view.rerender(<Harness enabled={false} size="xl" variant="female" />);
    expect(latest.dispose).toHaveBeenCalledOnce();
    expect(view.container.querySelector('canvas')).toBeNull();
    expect(view.container.querySelector('.lia-eyes')).toHaveAttribute('data-volume-ready', 'false');
    expect(binding.bind).toHaveBeenCalledTimes(2);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('never hides the fallback before a replacement canvas is painted at a committed layout', () => {
    const blankLayouts: HTMLSpanElement[] = [];
    const onLayout = (root: HTMLSpanElement) => {
      const canvas = root.querySelector<HTMLCanvasElement>('canvas');
      if (root.dataset.volumeReady === 'true' && canvas?.dataset.painted !== 'true')
        blankLayouts.push(root);
    };
    const view = render(<Harness enabled onLayout={onLayout} />);
    view.rerender(<Harness enabled variant="female" onLayout={onLayout} />);
    view.rerender(<Harness enabled variant="female" size="xl" onLayout={onLayout} />);
    expect(blankLayouts).toHaveLength(0);
  });
});

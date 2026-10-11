import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

import { ExpressiveEyes, type ExpressiveEyesProps } from '../ExpressiveEyes';
import { CHANNELS, type ChannelKey } from '../rig/channels';
import { createRigWriter } from '../rig/apply';
import { createEyeRig } from '../rig/runtime';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

const PAINT_CHANNELS = [
  'mouthOpen',
  'mouthW',
  'mouthSkew',
  'mouthArc',
  'syL',
  'syR',
  'lidTopL',
  'lidTopR',
  'lidBotL',
  'lidBotR',
  'rTopL',
  'rTopR',
  'strokeArcL',
  'strokeArcR',
  'strokeRoundL',
  'strokeRoundR',
] as const satisfies readonly ChannelKey[];

function paintedPortrait(root: HTMLElement) {
  return {
    channels: Object.fromEntries(
      PAINT_CHANNELS.map(key => [key, root.style.getPropertyValue(CHANNELS[key].cssVar)] as const)
    ),
    mouth: root.querySelector('[data-rig-mouth]')?.getAttribute('d'),
    eyes: ['L', 'R'].map(side => ({
      upper: root.querySelector(`[data-rig-stroke="${side}"]`)?.getAttribute('d'),
      lower: root.querySelector(`[data-rig-ring="${side}"]`)?.getAttribute('d'),
      opacity: root.querySelector(`[data-rig-ring="${side}"]`)?.getAttribute('opacity'),
    })),
  };
}

beforeEach(() => {
  installSpiritBrowser();
  // Hold the real shared scheduler before its first frame, rather than replacing the rig/writer.
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((_callback: FrameRequestCallback) => 1)
  );
  vi.stubGlobal(
    'cancelAnimationFrame',
    vi.fn((_id: number) => {})
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useEyesRig — waking an updated historical portrait', () => {
  it('starts with the latest committed mouth, eye contours and lids before any animation frame', () => {
    const first: ExpressiveEyesProps = {
      expression: 'sad',
      styleId: 'cozmo',
      size: 'sm',
      gaze: null,
      life: false,
      staticPose: true,
      motionEnabled: false,
    };
    const { container, rerender, unmount } = render(<ExpressiveEyes {...first} />);
    const root = container.querySelector<HTMLElement>('.lia-eyes')!;
    const previous = paintedPortrait(root);
    const latest: ExpressiveEyesProps = {
      ...first,
      expression: 'joy',
      styleId: 'anneaux',
      idleFamily: 'lively',
      emphasis: 1.3,
      responseWeight: 0.7,
    };
    rerender(<ExpressiveEyes {...latest} />);
    const resting = paintedPortrait(root);
    expect(resting).not.toEqual(previous);
    expect(resting.mouth).toBeTruthy();
    expect(resting.eyes.every(eye => Boolean(eye.upper))).toBe(true);
    expect(Object.values(resting.channels).every(value => value !== '')).toBe(true);
    expect(activeFrameSubscribers()).toBe(0);
    expect(requestAnimationFrame).not.toHaveBeenCalled();

    // Animated mouths include their native breathing loops at time0. A fresh
    // real rig is the latest live pose, rather than the reduced-motion snapshot.
    const referenceRoot = root.cloneNode(true);
    if (!(referenceRoot instanceof HTMLElement))
      throw new Error('Portrait clone has no native host');
    const referenceRig = createEyeRig({
      initial: {
        expression: 'joy',
        styleId: 'anneaux',
        family: 'lively',
        emphasis: 1.3,
        responseWeight: 0.7,
      },
    });
    const referenceWriter = createRigWriter(referenceRoot);
    referenceWriter.write(referenceRig.values());
    const livePose = paintedPortrait(referenceRoot);
    referenceWriter.dispose();

    rerender(<ExpressiveEyes {...latest} staticPose={false} motionEnabled />);
    expect(container.querySelector('.lia-eyes')).toBe(root);
    expect(activeFrameSubscribers()).toBe(1);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    const awakened = paintedPortrait(root);
    expect(awakened).toEqual(livePose);
    expect(awakened.eyes).toEqual(resting.eyes);
    for (const key of PAINT_CHANNELS.filter(channel => !channel.startsWith('mouth'))) {
      expect(awakened.channels[key]).toBe(resting.channels[key]);
    }

    unmount();
    expect(activeFrameSubscribers()).toBe(0);
  });
});

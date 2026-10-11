import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { ExpressiveEyes } from '../ExpressiveEyes';
import * as runtime from '../rig/runtime';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

beforeEach(() => {
  installSpiritBrowser();
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

describe('character identity uses the committed native rig', () => {
  it('paints the same warm neutral before any frame in static and live portraits, including a frozen identity change', () => {
    // Compare the authored base without the existing phase-shifted breathing.
    installSpiritBrowser(true);
    const portrait = (characterId: 'orbit' | 'oscar', staticPose: boolean) => (
      <ExpressiveEyes
        expression="neutral"
        styleId="billes"
        characterId={characterId}
        gaze={null}
        size="sm"
        life={false}
        sculptedFace
        staticPose={staticPose}
        motionEnabled={!staticPose}
      />
    );
    const view = render(portrait('orbit', true));
    const curve = () =>
      Number(
        (view.container.querySelector('.lia-eyes') as HTMLElement).style.getPropertyValue(
          '--rig-mouth-curve'
        )
      );
    const mouth = () => view.container.querySelector('[data-rig-mouth]')?.getAttribute('d');
    expect(curve()).toBeGreaterThanOrEqual(0.32);
    expect(activeFrameSubscribers()).toBe(0);
    view.rerender(portrait('oscar', true));
    expect(curve()).toBeGreaterThanOrEqual(0.32);
    const stillCurve = curve();
    const stillMouth = mouth();
    view.rerender(portrait('oscar', false));
    expect(curve()).toBe(stillCurve);
    expect(mouth()).toBe(stillMouth);
    view.unmount();
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('changes identity before authoring a simultaneous fear reaction, without rebuilding the rig', () => {
    const real = runtime.createEyeRig;
    let captured: runtime.EyeRig | undefined;
    const factory = vi.spyOn(runtime, 'createEyeRig').mockImplementation(options => {
      captured = real(options);
      return captured;
    });
    const view = render(
      <ExpressiveEyes
        expression="neutral"
        styleId="billes"
        characterId="orbit"
        gaze={null}
        size="md"
        life={false}
      />
    );
    if (!captured) throw new Error('Native rig did not mount');
    const rig = captured;
    rig.playScene('body-balloon');
    for (let frame = 0; frame < 45; frame++) rig.step(16);
    view.rerender(
      <ExpressiveEyes
        expression="fear"
        styleId="billes"
        characterId="bip"
        gaze={null}
        size="md"
        life={false}
      />
    );
    expect(factory).toHaveBeenCalledTimes(1);
    expect(rig.isPerforming()).toBe(false);
    let lift = 0;
    for (let frame = 0; frame < 12; frame++) {
      rig.step(16);
      lift = Math.min(lift, rig.values().massY);
    }
    expect(lift).toBeLessThan(-0.004);
    view.unmount();
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('wakes a frozen portrait with its latest character and keeps its authored bow available', () => {
    const real = runtime.createEyeRig;
    let captured: runtime.EyeRig | undefined;
    vi.spyOn(runtime, 'createEyeRig').mockImplementation(options => {
      captured = real(options);
      return captured;
    });
    const view = render(
      <ExpressiveEyes
        expression="neutral"
        characterId="orbit"
        gaze={null}
        size="sm"
        life={false}
        staticPose
        motionEnabled={false}
      />
    );
    view.rerender(
      <ExpressiveEyes
        expression="neutral"
        characterId="oscar"
        gaze={null}
        size="sm"
        life={false}
        staticPose
        motionEnabled={false}
      />
    );
    view.rerender(
      <ExpressiveEyes
        expression="neutral"
        characterId="oscar"
        gaze={null}
        size="sm"
        life={false}
        motionEnabled
      />
    );
    if (!captured) throw new Error('Native live portrait did not mount');
    captured.playScene('body-bow');
    for (let frame = 0; frame < 70; frame++) captured.step(16);
    expect(captured.values().headPitch).toBeGreaterThan(0.4);
    expect(captured.values().bodySy).toBeLessThan(0.95);
    view.unmount();
    expect(activeFrameSubscribers()).toBe(0);
  });
});

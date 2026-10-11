import { afterEach, describe, expect, it, vi } from 'vitest';
import { bindBodyMotion } from '../body-motion-binding';
import { createEyeRig } from '../runtime';
import { createRigWriter } from '../apply';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';

afterEach(() => document.body.replaceChildren());

function mount() {
  const host = document.createElement('div');
  host.className = 'lia-eyes-widget';
  host.innerHTML = '<span class="lia-eyes" style="font-size:20px"></span><button>drag</button>';
  document.body.append(host);
  const element = host.firstElementChild as HTMLElement;
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    left: 80,
    top: 80,
    width: 52,
    height: 52,
    right: 132,
    bottom: 132,
    x: 80,
    y: 80,
    toJSON: () => ({}),
  });
  const rig = createEyeRig();
  const writer = createRigWriter(element);
  const wake = vi.fn();
  const dispose = bindBodyMotion(element, rig, writer, wake);
  return { host, element, rig, writer, wake, dispose };
}

describe('body interaction priority', () => {
  it('repaints the clamped resting body after a mobile resize without waking a frame', async () => {
    const previousPreferences = useEyesWidgetStore.getState();
    const previousStorage = localStorage.getItem(EYES_WIDGET_PREFS_KEY);
    useEyesWidgetStore.setState({ size: 'xl', position: { xPct: 99, yPct: 99 } });
    const preferences = useEyesWidgetStore.getState();
    vi.stubGlobal('visualViewport', undefined);
    vi.stubGlobal('innerWidth', 640);
    vi.stubGlobal('innerHeight', 640);

    const host = document.createElement('div');
    host.className = 'lia-eyes-widget';
    host.style.left = '99%';
    host.style.top = '99%';
    const element = document.createElement('span');
    element.className = 'lia-eyes';
    element.style.fontSize = '64px';
    host.append(element);
    document.body.append(host);
    let rect = new DOMRect(620, 147.6, 166.4, 166.4);
    vi.spyOn(element, 'getBoundingClientRect').mockImplementation(() => rect);
    const rig = createEyeRig({ reducedMotion: true });
    const writer = createRigWriter(element);
    // A suspended host can receive wake requests without running a frame.
    const wake = vi.fn();
    const dispose = bindBodyMotion(element, rig, writer, wake);
    try {
      writer.write(rig.values());
      expect(parseFloat(element.style.getPropertyValue('--rig-body-x'))).toBeLessThan(0);
      expect(rig.values().bodyX).toBe(0);
      wake.mockClear();

      vi.stubGlobal('innerWidth', 320);
      window.dispatchEvent(new Event('resize'));
      expect(parseFloat(element.style.getPropertyValue('--rig-body-x'))).toBeLessThan(0);
      // React's host-style commit happens after resize. The real mutation
      // observer must repaint its final bounds while the clock stays stopped.
      rect = new DOMRect(147.6, 147.6, 166.4, 166.4);
      host.style.left = '147.6px';
      await Promise.resolve();

      expect(wake).toHaveBeenCalledTimes(2);
      expect(rig.values().bodyX).toBe(0);
      expect(useEyesWidgetStore.getState()).toBe(preferences);
      expect(element.style.getPropertyValue('--rig-body-x')).toBe('0em');
    } finally {
      dispose();
      writer.dispose();
      vi.unstubAllGlobals();
      useEyesWidgetStore.setState(previousPreferences, true);
      if (previousStorage === null) localStorage.removeItem(EYES_WIDGET_PREFS_KEY);
      else localStorage.setItem(EYES_WIDGET_PREFS_KEY, previousStorage);
    }
  });
  it('retains focus and hover priority when the face remounts inside its existing shell', () => {
    const { host, element, writer, wake, dispose } = mount();
    dispose();
    const button = host.querySelector('button')!;
    button.focus();
    const focusedRig = createEyeRig();
    const unbindFocused = bindBodyMotion(element, focusedRig, writer, wake);
    focusedRig.playScene('body-hops');
    expect(focusedRig.isPerforming()).toBe(false);
    button.blur();
    focusedRig.playScene('body-hops');
    expect(focusedRig.isPerforming()).toBe(true);
    unbindFocused();

    vi.spyOn(host, 'matches').mockImplementation(selector => selector === ':hover');
    const hoveredRig = createEyeRig();
    const unbindHovered = bindBodyMotion(element, hoveredRig, writer, wake);
    hoveredRig.playScene('body-roll');
    expect(hoveredRig.isPerforming()).toBe(false);
    host.dispatchEvent(new Event('pointerleave'));
    hoveredRig.playScene('body-roll');
    expect(hoveredRig.isPerforming()).toBe(true);
    unbindHovered();
  });
  it('does not subscribe comparison cards to global input or layout events', () => {
    const element = document.createElement('span');
    element.style.fontSize = '20px';
    document.body.append(element);
    const rig = createEyeRig();
    const writer = createRigWriter(element);
    const wake = vi.fn();
    const dispose = bindBodyMotion(element, rig, writer, wake);
    wake.mockClear();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    document.dispatchEvent(new Event('pointerdown'));
    document.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('resize'));
    expect(wake).not.toHaveBeenCalled();
    dispose();
  });
  it('yields to hovering and typing, resumes later, and removes its event bindings', () => {
    const { host, rig, wake, dispose } = mount();
    rig.playScene('body-roll');
    expect(rig.isPerforming()).toBe(true);
    host.dispatchEvent(new Event('pointerenter'));
    expect(rig.isPerforming()).toBe(false);
    rig.playScene('body-hops');
    expect(rig.isPerforming()).toBe(false);
    host.dispatchEvent(new Event('pointerleave'));
    rig.playScene('body-hops');
    expect(rig.isPerforming()).toBe(true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    expect(rig.isPerforming()).toBe(false);
    rig.playScene('body-jig');
    expect(rig.isPerforming()).toBe(false);
    for (let i = 0; i < 100; i++) rig.step(16);
    rig.playScene('body-jig');
    expect(rig.isPerforming()).toBe(true);
    dispose();
    wake.mockClear();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' }));
    host.dispatchEvent(new Event('pointerenter'));
    expect(wake).not.toHaveBeenCalled();
    expect(rig.isPerforming()).toBe(true);
  });

  it('keeps controls at the anchor and gives their focus priority over a scene', () => {
    const { host, element, rig, writer, dispose } = mount();
    const button = host.querySelector('button')!;
    rig.playScene('body-balloon');
    for (let i = 0; i < 70; i++) rig.step(16);
    writer.write(rig.values());
    expect(element.dataset.bodyMoving).toBe('true');
    expect(button.style.transform).toBe('');
    button.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    expect(rig.isPerforming()).toBe(false);
    rig.playScene('body-roll');
    expect(rig.isPerforming()).toBe(false);
    button.dispatchEvent(
      new FocusEvent('focusout', { bubbles: true, relatedTarget: document.body })
    );
    rig.playScene('body-roll');
    expect(rig.isPerforming()).toBe(true);
    dispose();
  });
});

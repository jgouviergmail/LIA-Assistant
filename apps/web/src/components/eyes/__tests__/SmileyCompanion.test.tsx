import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { ExpressiveEyes, type ExpressiveEyesProps } from '../ExpressiveEyes';
import { EYE_EXPRESSIONS } from '../expression-engine';
import { CHANNEL_KEYS, CHANNELS } from '../rig/channels';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';
import { SpiritIntersectionObserver } from '@/components/spirit/__tests__/browser';
import * as sphereBinding from '../smiley/sphere-binding';
import { sphereGraphics } from './sphere-graphics';

let clock = 0;
let frameId = 0;
const frames = new Map<number, FrameRequestCallback>();

function advanceFrames(duration: number) {
  act(() => {
    for (let elapsed = 0; elapsed < duration; elapsed += 16) {
      clock += 16;
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach(frame => frame(clock));
    }
  });
}

function root(container: HTMLElement) {
  const element = container.querySelector<HTMLElement>('.lia-eyes');
  if (!element) throw new Error('The actual native Smiley rig must mount');
  return element;
}

function expectFaceBoundary(container: HTMLElement) {
  const face = root(container);
  const head = face.querySelector('.lia-head')!;
  const boundary = head.querySelector('.lia-raster-face-mask')!;
  expect(boundary.parentElement).toBe(head);
  expect(boundary.querySelectorAll('.lia-eye-shape')).toHaveLength(2);
  expect(boundary.querySelectorAll('.lia-eye-blink')).toHaveLength(2);
  expect(boundary.querySelectorAll('[data-rig-mouth]')).toHaveLength(1);
  expect(boundary.querySelector('[data-rig-brow]')).toBeNull();
  const brows = head.querySelector('.lia-raster-brows')!;
  expect(brows.parentElement).toBe(head);
  expect(brows.querySelectorAll('[data-rig-brow-shape="sculpted"]')).toHaveLength(2);
  expect(brows.querySelector('.lia-eye-shape')).toBeNull();
  const pupils = [...boundary.querySelectorAll('.lia-eye-pupil')];
  expect(pupils).toHaveLength(2);
  for (const pupil of pupils) {
    expect(pupil.parentElement).toHaveClass('lia-eye-pupil-clip');
    expect(pupil.closest('.lia-eye-shape')).not.toBeNull();
    expect(pupil.parentElement).not.toHaveAttribute('style');
  }
  expect(face).toHaveClass('lia-smiley');
  expect(face).toHaveAttribute('data-style', 'smiley');
  expect(face.querySelector('.lia-avatar-body')).not.toBeNull();
  expect(face.querySelector('[data-spirit-companion]')).toBeNull();
}

beforeEach(() => {
  installSpiritBrowser();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.spyOn(Math, 'random').mockReturnValue(0.5);
  clock = 0;
  frames.clear();
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => {
    frames.set(++frameId, frame);
    return frameId;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Smiley original raster body with its actual native face', () => {
  it('wakes the same active rig for male/female attachment changes without another subscriber', () => {
    const props: ExpressiveEyesProps = {
      styleId: 'smiley',
      expression: 'neutral',
      gaze: { x: 1, y: -1 },
      size: 'sm',
      life: false,
    };
    const view = render(<ExpressiveEyes {...props} />);
    const host = root(view.container);
    advanceFrames(80);
    expect(activeFrameSubscribers()).toBe(1);
    view.rerender(<ExpressiveEyes {...props} smileyVariant="female" />);
    advanceFrames(48);
    expect(root(view.container)).toBe(host);
    expect(host.querySelector<HTMLElement>('.lia-smiley-ribbon')?.style.transform).toContain(
      'matrix('
    );
    expect(activeFrameSubscribers()).toBe(1);
    view.rerender(<ExpressiveEyes {...props} smileyVariant="male" />);
    advanceFrames(48);
    expect(host.querySelector('.lia-smiley-ribbon')).toBeNull();
    expect(activeFrameSubscribers()).toBe(1);
    view.unmount();
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('updates reduced-motion female/male snapshots and returns to an idle stopped clock', () => {
    installSpiritBrowser(true);
    const props: ExpressiveEyesProps = {
      styleId: 'smiley',
      expression: 'neutral',
      gaze: null,
      size: 'sm',
      life: false,
    };
    const view = render(<ExpressiveEyes {...props} />);
    for (const smileyVariant of ['female', 'male', 'female'] as const) {
      view.rerender(<ExpressiveEyes {...props} smileyVariant={smileyVariant} />);
      advanceFrames(64);
      expect(root(view.container)).toHaveAttribute('data-smiley-variant', smileyVariant);
      expect(activeFrameSubscribers()).toBe(0);
      if (smileyVariant === 'female')
        expect(
          root(view.container).querySelector<HTMLElement>('.lia-smiley-ribbon')?.style.transform
        ).toContain('matrix(');
    }
  });
  it('switches the gender on the same host, attaching female lashes and a projected ribbon without changing acting', () => {
    const props: ExpressiveEyesProps = {
      styleId: 'smiley',
      expression: 'neutral',
      gaze: { x: 1, y: -1 },
      size: 'sm',
      motionEnabled: false,
      life: false,
    };
    const view = render(<ExpressiveEyes {...props} />);
    const host = root(view.container);
    expect(host).toHaveAttribute('data-smiley-variant', 'male');
    expect(host.querySelector('.lia-smiley-ribbon')).toBeNull();
    expect(host.querySelector('.lia-smiley-upper-lashes')).toBeNull();
    const channels = CHANNEL_KEYS.map(channel =>
      host.style.getPropertyValue(CHANNELS[channel].cssVar)
    );
    view.rerender(<ExpressiveEyes {...props} smileyVariant="female" />);
    expect(root(view.container)).toBe(host);
    expect(host).toHaveAttribute('data-smiley-variant', 'female');
    expect(host.querySelectorAll('.lia-smiley-upper-lashes')).toHaveLength(2);
    expect(host.querySelector<HTMLElement>('.lia-smiley-ribbon')?.style.transform).toContain(
      'matrix('
    );
    expect(host.querySelector('.lia-smiley-ribbon')?.closest('.lia-raster-face-mask')).toBeNull();
    expect(
      CHANNEL_KEYS.map(channel => host.style.getPropertyValue(CHANNELS[channel].cssVar))
    ).toEqual(channels);
    view.rerender(<ExpressiveEyes {...props} smileyVariant="male" />);
    expect(host.querySelector('.lia-smiley-ribbon')).toBeNull();
    expect(host.querySelector('.lia-smiley-upper-lashes')).toBeNull();
    expect(activeFrameSubscribers()).toBe(0);
  });
  it('suspends real GPU draws with the native viewport/document owner and resumes without adding a frame subscriber', () => {
    const gl = sphereGraphics();
    const bind = sphereBinding.bindSmileySphere;
    vi.spyOn(sphereBinding, 'bindSmileySphere').mockImplementation((canvas, host) =>
      bind(canvas, host, gl)
    );
    let hidden = false;
    vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
    const props: ExpressiveEyesProps = {
      styleId: 'smiley',
      expression: 'neutral',
      gaze: { x: 1, y: -1 },
      size: 'sm',
      life: false,
    };
    const view = render(<ExpressiveEyes {...props} />);
    const host = root(view.container);
    const observer = SpiritIntersectionObserver.instances.find(instance =>
      instance.targets.has(host)
    )!;
    observer.notify(host, true);
    advanceFrames(160);
    expect(activeFrameSubscribers()).toBe(1);
    const initialDraws = gl.drawArrays.mock.calls.length;
    expect(initialDraws).toBeGreaterThan(0);
    view.rerender(<ExpressiveEyes {...props} gaze={{ x: -1, y: 1 }} />);
    advanceFrames(160);
    expect(gl.drawArrays.mock.calls.length).toBeGreaterThan(initialDraws);
    observer.notify(host, false);
    const stopped = gl.drawArrays.mock.calls.length;
    advanceFrames(320);
    expect(gl.drawArrays).toHaveBeenCalledTimes(stopped);
    expect(activeFrameSubscribers()).toBe(0);
    observer.notify(host, true);
    advanceFrames(80);
    expect(gl.drawArrays.mock.calls.length).toBeGreaterThan(stopped);
    hidden = true;
    document.dispatchEvent(new Event('visibilitychange'));
    const hiddenDraws = gl.drawArrays.mock.calls.length;
    view.rerender(<ExpressiveEyes {...props} gaze={{ x: 1, y: -1 }} />);
    advanceFrames(320);
    expect(gl.drawArrays).toHaveBeenCalledTimes(hiddenDraws);
    expect(activeFrameSubscribers()).toBe(0);
    hidden = false;
    document.dispatchEvent(new Event('visibilitychange'));
    advanceFrames(160);
    expect(gl.drawArrays.mock.calls.length).toBeGreaterThan(hiddenDraws);
    view.unmount();
    expect(activeFrameSubscribers()).toBe(0);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(1);
  });

  it('settles reduced-motion snapshots and resizing without recurring GPU frames', () => {
    installSpiritBrowser(true);
    const gl = sphereGraphics();
    const bind = sphereBinding.bindSmileySphere;
    vi.spyOn(sphereBinding, 'bindSmileySphere').mockImplementation((canvas, host) =>
      bind(canvas, host, gl)
    );
    const props: ExpressiveEyesProps = {
      styleId: 'smiley',
      expression: 'neutral',
      gaze: null,
      size: 'sm',
      life: false,
    };
    const view = render(<ExpressiveEyes {...props} />);
    advanceFrames(64);
    const still = gl.drawArrays.mock.calls.length;
    advanceFrames(1000);
    expect(gl.drawArrays).toHaveBeenCalledTimes(still);
    expect(activeFrameSubscribers()).toBe(0);
    view.rerender(<ExpressiveEyes {...props} size="lg" expression="joy" />);
    advanceFrames(64);
    expect(view.container.querySelector('canvas')?.width).toBe(115);
    const resized = gl.drawArrays.mock.calls.length;
    advanceFrames(1000);
    expect(gl.drawArrays).toHaveBeenCalledTimes(resized);
    expect(activeFrameSubscribers()).toBe(0);
  });
  it('enters and re-enters the spherical style on the same native host and writes its newly mounted face', () => {
    const props: ExpressiveEyesProps = {
      styleId: 'cozmo',
      expression: 'joy',
      gaze: { x: 1, y: -1 },
      size: 'sm',
      motionEnabled: false,
      life: false,
    };
    const view = render(<ExpressiveEyes {...props} />);
    const host = root(view.container);
    for (const styleId of ['smiley', 'cozmo', 'smiley'] as const) {
      view.rerender(<ExpressiveEyes {...props} styleId={styleId} />);
      expect(root(view.container)).toBe(host);
      if (styleId !== 'smiley') continue;
      const surfaces = [...host.querySelectorAll<HTMLElement>('[data-smiley-surface]')];
      expect(surfaces).toHaveLength(5);
      expect(surfaces.every(surface => surface.style.transform.includes('matrix('))).toBe(true);
      expect(host.querySelector('[data-rig-mouth]')?.getAttribute('d')).not.toBe('');
    }
    expect(activeFrameSubscribers()).toBe(0);
  });
  it('does not let optional false flags remove the Smiley body or iris boundary', () => {
    const { container } = render(
      <ExpressiveEyes
        styleId="smiley"
        expression="neutral"
        gaze={null}
        size="sm"
        faceMask={false}
        pupilClip={false}
        motionEnabled={false}
      />
    );
    expectFaceBoundary(container);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('contains every expression in the body boundary, with free sculpted brows and stationary iris wrappers', () => {
    const { container, rerender } = render(
      <ExpressiveEyes
        styleId="smiley"
        expression="neutral"
        gaze={null}
        size="sm"
        motionEnabled={false}
      />
    );
    for (const expression of EYE_EXPRESSIONS) {
      rerender(
        <ExpressiveEyes
          styleId="smiley"
          expression={expression}
          gaze={null}
          size="sm"
          motionEnabled={false}
        />
      );
      expectFaceBoundary(container);
      expect(root(container)).toHaveAttribute('data-expression', expression);
    }
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('keeps native acting channels consistent when optional boundary flags are false', () => {
    const initial: ExpressiveEyesProps = {
      styleId: 'smiley',
      expression: 'neutral',
      gaze: null,
      size: 'md',
      life: false,
    };
    const decorated = render(<ExpressiveEyes {...initial} />);
    const explicitFlags = render(
      <ExpressiveEyes {...initial} faceMask={false} pupilClip={false} />
    );
    for (const variation of [
      { expression: 'surprise', gaze: { x: 1, y: -1 }, blinking: true, blinkMask: true },
      { expression: 'speaking', gaze: { x: -1, y: 1 }, blinking: false, gesture: 'bounce' },
      {
        expression: 'joy',
        gaze: { x: 1, y: 1 },
        gesture: 'tilt',
        emphasis: 1.4,
        responseWeight: 0.7,
      },
    ] satisfies Partial<ExpressiveEyesProps>[]) {
      const props = {
        ...initial,
        ...variation,
        gazeDurationMs: 120,
        idleFamily: 'lively' as const,
        emote: '!',
        emoteLeaving: true,
        accessory: 'sparkle' as const,
      };
      decorated.rerender(<ExpressiveEyes {...props} />);
      explicitFlags.rerender(<ExpressiveEyes {...props} faceMask={false} pupilClip={false} />);
      for (const duration of [112, 208, 400]) {
        advanceFrames(duration);
        expectFaceBoundary(decorated.container);
        expectFaceBoundary(explicitFlags.container);
        for (const channel of CHANNEL_KEYS) {
          expect(root(decorated.container).style.getPropertyValue(CHANNELS[channel].cssVar)).toBe(
            root(explicitFlags.container).style.getPropertyValue(CHANNELS[channel].cssVar)
          );
        }
      }
      expect(root(decorated.container)).toHaveAttribute('data-gaze-ms', '120');
      expect(decorated.container.querySelector('.lia-emote')).toHaveClass('is-leaving');
      expect(decorated.container.querySelector('.lia-accessory')).toHaveAttribute(
        'data-accessory',
        'sparkle'
      );
    }
    expect(activeFrameSubscribers()).toBe(2);
  });
});

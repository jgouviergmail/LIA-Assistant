import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { ExpressiveEyes, type ExpressiveEyesProps } from '../ExpressiveEyes';
import { MonitorCompanion } from '../MonitorCompanion';
import { EYE_EXPRESSIONS } from '../expression-engine';
import { RIG_EYE_STYLE_IDS } from '../eye-styles';
import { CHANNELS, CHANNEL_KEYS } from '../rig/channels';
import { activeFrameSubscribers } from '../rig/scheduler';
import { MONITOR_SCREEN } from '../monitor-geometry';
import {
  installSpiritBrowser,
  SpiritIntersectionObserver,
} from '@/components/spirit/__tests__/browser';

const styles = RIG_EYE_STYLE_IDS.filter(style => style !== 'smiley');
let clock = 0;
let frameId = 0;
const frames = new Map<number, FrameRequestCallback>();
let browser: ReturnType<typeof installSpiritBrowser>;

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
  if (!element) throw new Error('The native face must be mounted');
  return element;
}

function expectScreenContainment(container: HTMLElement) {
  const screen = container.querySelector('.lia-monitor-screen');
  const brows = container.querySelector('.lia-monitor-brows');
  expect(screen).toBeInTheDocument();
  for (const graphic of container.querySelectorAll<HTMLElement | SVGElement>(
    '.lia-eye-blink, .lia-eye-shape, .lia-eye-pupil, .lia-eye-contour, .lia-mouth'
  )) {
    expect(screen).toContainElement(graphic);
  }
  expect(screen?.querySelectorAll('.lia-eye-shape')).toHaveLength(2);
  expect(screen?.querySelector('[data-rig-mouth]')).toBeInTheDocument();
  expect(screen?.querySelector('.lia-eye-brow')).toBeNull();
  expect(brows?.querySelectorAll('[data-rig-brow]')).toHaveLength(2);
  expect(brows?.closest('.lia-monitor-screen')).toBeNull();
  expect(container.querySelectorAll('[data-rig-brow]')).toHaveLength(2);
}

beforeEach(() => {
  browser = installSpiritBrowser();
  vi.spyOn(document, 'hidden', 'get').mockImplementation(
    () => document.visibilityState === 'hidden'
  );
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

describe('Monitor companion decoration', () => {
  it.each(styles)(
    '%s keeps all expression graphics under the screen mask, with brows outside',
    styleId => {
      const { container, rerender } = render(
        <MonitorCompanion
          styleId={styleId}
          expression="neutral"
          gaze={null}
          size="sm"
          life={false}
        />
      );
      for (const expression of EYE_EXPRESSIONS) {
        rerender(
          <MonitorCompanion
            styleId={styleId}
            expression={expression}
            gaze={null}
            size="sm"
            life={false}
          />
        );
        expectScreenContainment(container);
        expect(root(container)).toHaveAttribute('data-style', styleId);
      }
      expect(root(container)).toHaveClass('lia-monitor');
      expect(root(container)).toHaveAttribute('aria-hidden', 'true');
      expect(activeFrameSubscribers()).toBe(1);
    }
  );

  it.each(styles)(
    '%s preserves every rig channel through gaze extremes, blinks, speech and gestures',
    styleId => {
      const initial: ExpressiveEyesProps = {
        styleId,
        expression: 'neutral',
        gaze: null,
        size: 'md',
        life: false,
      };
      const monitor = render(<MonitorCompanion {...initial} />);
      const native = render(<ExpressiveEyes {...initial} />);
      for (const variation of [
        { expression: 'surprise', gaze: { x: 1, y: -1 }, blinking: true, blinkMask: true },
        { expression: 'speaking', gaze: { x: -1, y: 1 }, gesture: 'bounce', blinking: false },
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
        };
        monitor.rerender(<MonitorCompanion {...props} />);
        native.rerender(<ExpressiveEyes {...props} />);
        for (const duration of [112, 208, 400]) {
          advanceFrames(duration);
          expectScreenContainment(monitor.container);
          for (const channel of CHANNEL_KEYS) {
            expect(root(monitor.container).style.getPropertyValue(CHANNELS[channel].cssVar)).toBe(
              root(native.container).style.getPropertyValue(CHANNELS[channel].cssVar)
            );
          }
        }
      }
      expect(activeFrameSubscribers()).toBe(2);
    }
  );

  it('uses the actual asset screen geometry and a stationary rounded clipping parent', () => {
    const { container } = render(
      <MonitorCompanion
        expression="neutral"
        gaze={null}
        size="lg"
        motionEnabled={false}
        emote="!"
        accessory="sparkle"
      />
    );
    const face = root(container);
    expect(face.style.getPropertyValue('--screen-left')).toBe(`${MONITOR_SCREEN.x * 100}%`);
    expect(face.style.getPropertyValue('--screen-top')).toBe(`${MONITOR_SCREEN.y * 100}%`);
    expect(face.style.getPropertyValue('--screen-width')).toBe(`${MONITOR_SCREEN.width * 100}%`);
    expect(face.style.getPropertyValue('--screen-height')).toBe(`${MONITOR_SCREEN.height * 100}%`);
    expect(container.querySelector('.lia-emote')).toHaveTextContent('!');
    expect(container.querySelector('.lia-accessory')).toHaveAttribute('data-accessory', 'sparkle');
    expect(activeFrameSubscribers()).toBe(0);
    const css = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');
    const mask = css.slice(css.indexOf('.lia-monitor .lia-monitor-screen {')).split('}')[0];
    expect(mask).toContain('overflow: hidden');
    expect(mask).toContain('clip-path: inset(0 round var(--screen-radius))');
    expect(mask).not.toContain('--rig-');
  });

  it('pauses the illuminated display with the native viewport, tab and preview owner', () => {
    const props: ExpressiveEyesProps = {
      styleId: 'cozmo',
      expression: 'neutral',
      gaze: null,
      size: 'sm',
      life: false,
    };
    const { container, rerender } = render(<MonitorCompanion {...props} motionEnabled={false} />);
    const face = root(container);
    expect(face).toHaveAttribute('data-rig-visible', 'false');
    act(() => SpiritIntersectionObserver.instances[0].notify(face, true));
    expect(face).toHaveAttribute('data-rig-visible', 'true');
    expect(face).toHaveAttribute('data-motion', 'off');
    expect(activeFrameSubscribers()).toBe(0);
    rerender(<MonitorCompanion {...props} motionEnabled />);
    const observer = SpiritIntersectionObserver.instances.at(-1)!;
    act(() => observer.notify(face, true));
    advanceFrames(112);
    expect(activeFrameSubscribers()).toBe(1);
    act(() => observer.notify(face, false));
    expect(face).toHaveAttribute('data-rig-visible', 'false');
    expect(activeFrameSubscribers()).toBe(0);
    act(() => observer.notify(face, true));
    act(() => browser.setVisibility('hidden'));
    expect(face).toHaveAttribute('data-rig-visible', 'false');
    expect(activeFrameSubscribers()).toBe(0);
    act(() => browser.setVisibility('visible'));
    expect(face).toHaveAttribute('data-rig-visible', 'true');
    act(() => browser.setMotion(true));
    advanceFrames(32);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('draws full toon brows and luminous glyphs on pale glass, with two suspended signal layers', () => {
    const css = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');
    const skin = css.slice(css.indexOf('.lia-monitor {'));
    expect(skin).toContain('--face-eye-depth: 0em');
    expect(skin).toContain('--face-mouth-depth: 0em');
    expect(skin).toContain('--eyes-color: #2492c4');
    expect(skin).toContain('--brow-color: #1c526f');
    expect(skin).toContain('--has-brow: 1');
    expect(skin).toContain("[data-rig-brow-shape='sculpted']");
    expect(skin).toContain('fill: var(--brow-color)');
    expect(skin).toContain('stroke: none');
    expect(skin).toContain('height: 0.6em');
    expect(skin).toContain('width: max(1.05em, calc(var(--eye-w, 1.3em) * 0.9))');
    expect(skin).toContain('mix-blend-mode: multiply');
    expect(skin).toContain('#dff3fc');
    expect(skin).toContain('box-shadow:');
    expect(skin).toContain('rotateY(calc(var(--rig-head-yaw, 0) * 22deg))');
    expect(skin).toContain('rotateX(calc(var(--rig-head-pitch, 0) * -14deg))');
    expect(skin).toContain('rotate(calc(var(--rig-tilt, 0deg) * 1.4))');
    expect(skin).toContain('.lia-monitor .lia-monitor-screen::before');
    expect(skin).toContain('.lia-monitor .lia-monitor-screen::after');
    expect(skin).toContain('animation: lia-monitor-backlight 4s ease-in-out infinite paused');
    expect(skin).toContain('animation: lia-monitor-signal 4s steps(1, end) infinite paused');
    expect(skin).toContain(".lia-monitor[data-rig-visible='true']:not([data-motion='off'])");
    const reduced = skin.slice(skin.indexOf('@media (prefers-reduced-motion: reduce)'));
    expect(reduced).toContain('animation: none');
  });

  it('shows both raised, one raised and frowned full brows from the original expression channels', () => {
    const { container, rerender } = render(
      <MonitorCompanion
        styleId="cozmo"
        expression="neutral"
        gaze={null}
        size="lg"
        life={false}
        motionEnabled={false}
      />
    );
    const paths = container.querySelectorAll<SVGPathElement>('[data-rig-brow]');
    expect(paths).toHaveLength(2);
    paths.forEach(path => {
      expect(path).toHaveAttribute('data-rig-brow-shape', 'sculpted');
      expect(path.getAttribute('d')).toMatch(/ Z$/);
    });
    const drawings: string[] = [];
    for (const expression of ['surprise', 'question', 'anger'] as const) {
      rerender(
        <MonitorCompanion
          styleId="cozmo"
          expression={expression}
          gaze={null}
          size="lg"
          life={false}
          motionEnabled={false}
        />
      );
      drawings.push([...paths].map(path => path.getAttribute('d')).join('|'));
      expectScreenContainment(container);
    }
    expect(new Set(drawings).size).toBe(3);
    expect(activeFrameSubscribers()).toBe(0);
  });
});

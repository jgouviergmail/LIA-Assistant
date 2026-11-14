import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { AmbientAccessories, SkyAccessories } from '../AmbientAccessories';
import { EyesFace } from '../EyesFace';
import { createRigWriter } from '../rig/apply';
import { CHANNEL_KEYS, restChannelValues, type ChannelKey } from '../rig/channels';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';
import { SCARF_WRAP_SEGMENTS } from '../volume/scarf-wrap';

/** The sheet as a browser reads it: comments out, one entry per rule. Read from
 * disk on purpose: a `?raw` CSS import comes back empty under vitest. */
function styleRules() {
  const code = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8').replace(
    /\/\*[\s\S]*?\*\//g,
    ''
  );
  return [...code.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selectors, block]) => ({
    selectors: selectors.split(',').map(selector => selector.trim().replace(/\s+/g, ' ')),
    display: /(?:^|;)\s*display\s*:\s*([a-z-]+)/.exec(block)?.[1] ?? null,
  }));
}

/** The rig channel that paints a slot, found in the rig's own table. */
function weatherChannel(kind: string): ChannelKey {
  const name = `weather${kind[0].toUpperCase()}${kind.slice(1)}`;
  const channel = CHANNEL_KEYS.find(candidate => candidate === name);
  if (!channel) throw new Error(`No rig channel paints the ${kind} slot`);
  return channel;
}

beforeEach(() => installSpiritBrowser());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('offline weather decorations', () => {
  it('provides ten decorative material slots without eager image or inline background requests', () => {
    const { container } = render(<AmbientAccessories />);
    for (const weather of [
      'rain',
      'storm',
      'cold',
      'freezing',
      'snow',
      'hot',
      'heat',
      'fog',
      'wind',
      'night',
    ]) {
      const slot = container.querySelector(`.lia-ambient-weather--${weather}`);
      expect(slot).toHaveAttribute('aria-hidden', 'true');
      expect(slot?.querySelectorAll('.lia-ambient-prop')).toHaveLength(weather === 'snow' ? 7 : 1);
      expect(slot?.querySelector('.lia-ambient-prop')).not.toHaveAttribute('style');
    }
    expect(container.querySelectorAll('img, canvas')).toHaveLength(0);
    expect(container.textContent).toBe('');
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('lets the weather happen around the face: drops, falling snow, a gust, a breath', () => {
    const { container } = render(<AmbientAccessories />);
    const rain = container.querySelector('.lia-ambient-weather--rain');
    expect(rain?.querySelectorAll('.lia-ambient-cloud')).toHaveLength(1);
    expect(rain?.querySelectorAll('.lia-ambient-drop')).toHaveLength(5);
    expect(rain?.querySelectorAll('.lia-ambient-rimdrop')).toHaveLength(3);
    const snow = container.querySelector('.lia-ambient-weather--snow');
    expect(snow?.querySelectorAll('.lia-ambient-cloud')).toHaveLength(1);
    expect(snow?.querySelectorAll('.lia-ambient-prop.lia-ambient-flake')).toHaveLength(7);
    const wind = container.querySelector('.lia-ambient-weather--wind');
    expect(wind?.querySelectorAll('.lia-ambient-gust-line')).toHaveLength(2);
    expect(wind?.querySelectorAll('.lia-ambient-prop.lia-ambient-gust-leaf')).toHaveLength(1);
    const breath = container.querySelector('.lia-ambient-weather--freezing.lia-ambient-breath');
    expect(breath?.querySelectorAll('.lia-ambient-breath-puff')).toHaveLength(1);
    // Every particle is placed and timed by the sheet, never by an inline style.
    expect(container.querySelectorAll('[style]')).toHaveLength(1);
    expect(container.querySelectorAll('img, canvas, svg')).toHaveLength(0);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('carries the drop and the flake a scene plays: one box each, placed by the sheet', () => {
    // The first drop of a rain lands on the head, the first flake of a snow on the
    // nose (ADR-294, 2026-11-13): drawn from the files the sheet installs, moved by
    // the channels the scene drives, never by a style or a timer of their own.
    const { container } = render(<AmbientAccessories />);
    for (const kind of ['drop', 'flake']) {
      const slot = container.querySelector(`.lia-ambient-weather--${kind}`);
      expect(slot, kind).toHaveAttribute('aria-hidden', 'true');
      expect(slot?.children, kind).toHaveLength(1);
      expect(slot?.querySelector(`.lia-ambient-scene-${kind}`), kind).not.toBeNull();
      expect(slot?.querySelectorAll('[style], img, canvas, svg'), kind).toHaveLength(0);
    }
  });

  it('brings the sky of an ordinary day on three boxes: the sun, its turning rays, a passing cloud', () => {
    // The sky is there most days, and every box under the face is restyled on
    // each frame the rig writes: the sun paints its glow and core itself.
    const { container } = render(<SkyAccessories />);
    const sun = container.querySelector('.lia-ambient-weather--sun');
    expect(sun).toHaveAttribute('aria-hidden', 'true');
    expect(sun?.querySelectorAll('.lia-sky-rays')).toHaveLength(1);
    const cloud = sun?.querySelector('.lia-ambient-weather--cloud');
    expect(cloud).toHaveAttribute('aria-hidden', 'true');
    expect(cloud?.children).toHaveLength(0);
    expect(container.querySelectorAll('*')).toHaveLength(3);
    expect(container.querySelectorAll('[style], img, canvas, svg')).toHaveLength(0);
    expect(container.textContent).toBe('');
  });

  it('keeps decoration out of historical portraits and enables its slots without a separate clock', () => {
    const { container, rerender } = render(
      <EyesFace
        styleId="nimbo"
        variant="female"
        expression="neutral"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
        staticPose
      />
    );
    expect(container.querySelector('.lia-ambient-weather')).toBeNull();
    rerender(
      <EyesFace
        styleId="nimbo"
        variant="female"
        expression="neutral"
        gaze={null}
        size="sm"
        life
        animate={false}
        staticPose
      />
    );
    // Nimbo's halves have separate paint ownership beside the rotating head;
    // all other weather props keep their original attachment inside the head.
    const slots = [...container.querySelectorAll('.lia-ambient-weather')];
    expect(
      slots.map(slot => [...slot.classList].find(name => name.startsWith('lia-ambient-weather--')))
    ).toEqual([
      // The sky does not ride the head: it stays where the day is.
      'lia-ambient-weather--sun',
      'lia-ambient-weather--cloud',
      'lia-ambient-weather--cold',
      'lia-ambient-weather--cold',
      'lia-ambient-weather--rain',
      'lia-ambient-weather--storm',
      'lia-ambient-weather--freezing',
      'lia-ambient-weather--freezing',
      'lia-ambient-weather--snow',
      'lia-ambient-weather--hot',
      'lia-ambient-weather--heat',
      'lia-ambient-weather--fog',
      'lia-ambient-weather--wind',
      'lia-ambient-weather--night',
      // What a scene carries rides the head, so it meets the head (2026-11-13).
      'lia-ambient-weather--drop',
      'lia-ambient-weather--flake',
    ]);
    const head = container.querySelector('.lia-head');
    const cold = container.querySelectorAll('.lia-ambient-weather--cold');
    expect(cold).toHaveLength(2);
    for (const half of cold) {
      expect(half).toHaveClass('lia-scarf-wrap');
      expect(half).toHaveAttribute('aria-hidden', 'true');
      expect(half.parentElement).toBe(head?.parentElement);
      expect(half.querySelectorAll('.lia-scarf-wrap-facet')).toHaveLength(SCARF_WRAP_SEGMENTS / 2);
      expect(half.querySelectorAll('.lia-scarf-wrap-layer')).toHaveLength(1);
    }
    expect(head?.querySelectorAll('.lia-ambient-weather')).toHaveLength(12);
    expect(container.querySelector('.lia-ambient-weather--sun')?.parentElement).toBe(
      container.querySelector('.lia-eyes')
    );
    expect(head?.querySelector('.lia-scarf-wrap')).toBeNull();
    expect(container.querySelectorAll('.lia-scarf-wrap-knot')).toHaveLength(1);
    expect(container.querySelectorAll('.lia-scarf-wrap-tail')).toHaveLength(1);
    expect(container.querySelectorAll('.lia-ambient-prop')).toHaveLength(15);
    expect(container.querySelectorAll('img, canvas')).toHaveLength(0);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('takes every slot out of the style tree until the rig announces its weather', () => {
    // A hidden slot is still restyled on every frame the rig writes. Measured
    // on the public page (2026-11-11): 59 of the avatar's 100 elements are
    // these slots, and taking them out removes about half of its style cost.
    // Three tables must agree for a slot to come back: the slots mounted, the
    // token the writer announces, and the rule keyed on that token.
    const { container } = render(
      <EyesFace
        styleId="nimbo"
        variant="female"
        expression="neutral"
        gaze={null}
        size="sm"
        life
        animate={false}
        staticPose
      />
    );
    const kinds = [
      ...new Set(
        [...container.querySelectorAll('.lia-ambient-weather')].flatMap(slot =>
          [...slot.classList]
            .filter(name => name.startsWith('lia-ambient-weather--'))
            .map(name => name.replace('lia-ambient-weather--', ''))
        )
      ),
    ];
    expect(kinds).toHaveLength(14);
    const rules = styleRules();
    const displayOf = (selector: string) =>
      rules.filter(rule => rule.selectors.includes(selector)).flatMap(rule => rule.display ?? []);
    expect(displayOf('.lia-ambient-weather')).toEqual(['none']);
    for (const kind of kinds) {
      const root = document.createElement('span');
      const writer = createRigWriter(root);
      writer.write({ ...restChannelValues(), [weatherChannel(kind)]: 1 });
      expect(root.dataset.weatherProps, kind).toBe(kind);
      writer.dispose();
      expect(
        displayOf(`[data-weather-props~='${kind}'] .lia-ambient-weather--${kind}`),
        kind
      ).toEqual(['block']);
    }
  });

  it('takes the fitted fallback scarf out of the style tree while the native cloth draws it', () => {
    // Kept in the tree and merely invisible, the fallback was restyled on
    // every frame: with cold weather the avatar cost what it did before
    // (measured 2026-11-11: 73 elements with a box, 35 without the fallback).
    const drawnByTheCloth = ".lia-eyes[data-volume-scarf-ready='true'] .lia-ambient-weather--cold";
    const rules = styleRules().filter(rule => rule.selectors.includes(drawnByTheCloth));
    expect(rules.map(rule => rule.display)).toEqual(['none']);
  });
});

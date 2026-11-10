import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { AmbientAccessories } from '../AmbientAccessories';
import { EyesFace } from '../EyesFace';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';
import { SCARF_WRAP_SEGMENTS } from '../volume/scarf-wrap';

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
      expect(slot?.querySelectorAll('.lia-ambient-prop')).toHaveLength(weather === 'snow' ? 3 : 1);
      expect(slot?.querySelector('.lia-ambient-prop')).not.toHaveAttribute('style');
    }
    expect(container.querySelectorAll('img, canvas')).toHaveLength(0);
    expect(container.textContent).toBe('');
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('shares one native fall wrapper across three separate edge snowflakes', () => {
    const { container } = render(<AmbientAccessories />);
    const snow = container.querySelector('.lia-ambient-weather--snow');
    const fall = snow?.querySelector('.lia-ambient-weather-fall--snow');
    expect(fall).toHaveClass('lia-ambient-weather-fall');
    expect(fall?.querySelectorAll('.lia-ambient-prop')).toHaveLength(3);
    for (const edge of ['a', 'b', 'c']) {
      expect(fall?.querySelector(`.lia-ambient-prop--snow-${edge}`)).toBeInTheDocument();
    }
    expect(snow?.querySelectorAll('.lia-ambient-weather-fall--snow')).toHaveLength(1);
    expect(snow?.querySelector('img, canvas')).toBeNull();
    expect(activeFrameSubscribers()).toBe(0);
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
      'lia-ambient-weather--cold',
      'lia-ambient-weather--cold',
      'lia-ambient-weather--rain',
      'lia-ambient-weather--storm',
      'lia-ambient-weather--freezing',
      'lia-ambient-weather--snow',
      'lia-ambient-weather--hot',
      'lia-ambient-weather--heat',
      'lia-ambient-weather--fog',
      'lia-ambient-weather--wind',
      'lia-ambient-weather--night',
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
    expect(head?.querySelectorAll('.lia-ambient-weather')).toHaveLength(9);
    expect(head?.querySelector('.lia-scarf-wrap')).toBeNull();
    expect(container.querySelectorAll('.lia-scarf-wrap-knot')).toHaveLength(1);
    expect(container.querySelectorAll('.lia-scarf-wrap-tail')).toHaveLength(1);
    expect(container.querySelectorAll('.lia-ambient-prop')).toHaveLength(11);
    expect(container.querySelectorAll('img, canvas')).toHaveLength(0);
    expect(activeFrameSubscribers()).toBe(0);
  });
});

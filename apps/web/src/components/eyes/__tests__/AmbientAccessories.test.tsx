import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { AmbientAccessories } from '../AmbientAccessories';
import { EyesFace } from '../EyesFace';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

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
    expect(container.querySelectorAll('.lia-ambient-prop')).toHaveLength(12);
    expect(container.querySelectorAll('img, canvas')).toHaveLength(0);
    expect(activeFrameSubscribers()).toBe(0);
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { EyesFace } from '../EyesFace';
import { HYBRID_EYE_STYLE_IDS } from '../eye-styles';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

beforeEach(() => {
  installSpiritBrowser();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('sculpted hybrid faces retain their real native projection', () => {
  it.each(HYBRID_EYE_STYLE_IDS)(
    'keeps %s organs contained and its teeth clipped by the live cavity',
    character => {
      const { container } = render(
        <EyesFace
          styleId={character}
          variant="female"
          expression="joy"
          gaze={null}
          size="sm"
          life={false}
          animate={false}
          staticPose
        />
      );
      const mouth = container.querySelector<SVGPathElement>('[data-rig-mouth]');
      expect(mouth?.closest('.lia-raster-face-mask')).not.toBeNull();
      expect(mouth?.getAttribute('d')).toBeTruthy();
      if (character === 'bip') {
        expect(mouth).not.toHaveAttribute('data-rig-mouth-shape');
        expect(container.querySelector('[data-rig-mouth-teeth]')).toBeNull();
      } else {
        expect(mouth).toHaveAttribute('data-rig-mouth-shape', 'sculpted');
        const clip = container.querySelector('clipPath');
        expect(clip?.querySelector('use')).toHaveAttribute('href', `#${mouth?.id}`);
        for (const organ of ['teeth', 'tongue']) {
          const path = container.querySelector(`[data-rig-mouth-${organ}]`);
          expect(path?.getAttribute('d')).toBeTruthy();
          expect(path?.closest('g')).toHaveAttribute('clip-path', `url(#${clip?.id})`);
        }
        expect(container.querySelectorAll('[data-rig-brow-shape="sculpted"]')).toHaveLength(2);
      }
      expect(activeFrameSubscribers()).toBe(0);
      expect(container.querySelector('canvas')).toBeNull();
    }
  );

  it('updates newly mounted teeth when the same live native rig changes from Bip to Oscar', () => {
    const { container, rerender } = render(
      <EyesFace
        styleId="bip"
        variant="female"
        expression="neutral"
        gaze={null}
        size="sm"
        life={false}
        animate
      />
    );
    act(() => vi.advanceTimersByTime(400));
    const face = container.querySelector('.lia-eyes');
    rerender(
      <EyesFace
        styleId="oscar"
        variant="female"
        expression="joy"
        gaze={null}
        size="sm"
        life={false}
        animate
      />
    );
    const teeth = container.querySelector('[data-rig-mouth-teeth]');
    const firstTeeth = teeth?.getAttribute('d');
    expect(firstTeeth).toBeTruthy();
    act(() => vi.advanceTimersByTime(640));
    expect(container.querySelector('.lia-eyes')).toBe(face);
    expect(activeFrameSubscribers()).toBe(1);
    expect(teeth?.getAttribute('d')).not.toBe(firstTeeth);
  });
});

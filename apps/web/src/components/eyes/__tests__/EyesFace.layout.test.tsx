import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { EyesFace } from '../EyesFace';
import { ExpressiveEyes } from '../ExpressiveEyes';
import { EYE_STYLE_IDS, isRigEyeStyle } from '../eye-styles';
import { volumeProfile } from '../volume/volume-geometry';
import { SMILEY_COLLAR } from '../volume/cloth-geometry';
import { avatarLayoutProfile } from '../layout-profiles';
import { activeFrameSubscribers } from '../rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

beforeEach(() => installSpiritBrowser());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('avatar landmarks follow the selected model and gender without new motion', () => {
  it.each(EYE_STYLE_IDS)('publishes both %s layouts on the actual native host', styleId => {
    const view = render(
      <EyesFace
        styleId={styleId}
        variant="male"
        expression="joy"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
        staticPose
      />
    );
    for (const variant of ['male', 'female'] as const) {
      view.rerender(
        <EyesFace
          styleId={styleId}
          variant={variant}
          expression="joy"
          gaze={null}
          size="sm"
          life={false}
          animate={false}
          staticPose
        />
      );
      const root = view.container.querySelector<HTMLElement>('.lia-eyes');
      expect(root).toHaveAttribute('data-avatar-layout');
      expect(root).toHaveAttribute('data-avatar-variant', variant);
      expect(root).toHaveAttribute('data-expression', 'joy');
      for (const token of ['crown-y', 'face-y', 'neck-y']) {
        const value = root?.style.getPropertyValue(`--avatar-${token}`) ?? '';
        expect(value).toMatch(/^-?[\d.]+%$/);
        expect(parseFloat(value)).toBeGreaterThanOrEqual(-10);
        expect(parseFloat(value)).toBeLessThanOrEqual(100);
      }
      expect(root?.style.getPropertyValue('--avatar-face-half-width')).toContain('var(--eye-w');
      const scale = parseFloat(root?.style.getPropertyValue('--avatar-accessory-scale') ?? '');
      expect(scale).toBeGreaterThan(0);
      expect(scale).toBeLessThanOrEqual(1.2);
      const collar =
        styleId === 'smiley'
          ? SMILEY_COLLAR
          : volumeProfile(isRigEyeStyle(styleId) ? 'monitor' : styleId, variant).collar;
      expect(parseFloat(root?.style.getPropertyValue('--avatar-neck-y') ?? '')).toBeCloseTo(
        (collar.centerY / 2.6 + 0.5) * 100,
        3
      );
      const scarfWidth = root?.style.getPropertyValue('--avatar-scarf-width') ?? '';
      expect(scarfWidth).toMatch(/^[\d.]+em$/);
      expect(parseFloat(scarfWidth)).toBeCloseTo(2 * collar.radiusX * 1.1, 5);
      expect(view.container.querySelector('canvas')).toBeNull();
      expect(activeFrameSubscribers()).toBe(0);
    }
  });

  it('keeps Oscar and the feminine ribbon crowns distinct while preserving the saved pose', () => {
    const view = render(
      <EyesFace
        styleId="oscar"
        variant="male"
        expression="worried"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
        staticPose
      />
    );
    const male = view.container.querySelector<HTMLElement>('.lia-eyes');
    const maleCrown = male?.style.getPropertyValue('--avatar-crown-y');
    view.rerender(
      <EyesFace
        styleId="oscar"
        variant="female"
        expression="worried"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
        staticPose
      />
    );
    const female = view.container.querySelector<HTMLElement>('.lia-eyes');
    expect(female).toBe(male);
    expect(female?.style.getPropertyValue('--avatar-crown-y')).not.toBe(maleCrown);
    expect(female).toHaveAttribute('data-expression', 'worried');
    expect(female?.style.getPropertyValue('--avatar-face-half-width')).toContain('var(--eye-gap');
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('leaves bare native eyes outside the avatar layout contract', () => {
    const { container } = render(
      <ExpressiveEyes
        styleId="cozmo"
        expression="neutral"
        gaze={null}
        size="sm"
        life={false}
        motionEnabled={false}
        layoutProfile={avatarLayoutProfile('monitor', 'female')}
        screenBounds={{ x: 0.1, y: 0.2, width: 0.6, height: 0.4, radius: 0.02 }}
      />
    );
    const root = container.querySelector<HTMLElement>('.lia-eyes');
    expect(root).not.toHaveAttribute('data-avatar-layout');
    expect(root?.style.getPropertyValue('--avatar-crown-y')).toBe('');
    expect(root?.style.getPropertyValue('--screen-left')).toBe('10%');
    expect(root?.style.getPropertyValue('--screen-top')).toBe('20%');
    expect(activeFrameSubscribers()).toBe(0);
  });
});

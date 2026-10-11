import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { EyesFace } from '../EyesFace';
import { HYBRID_EYE_STYLE_IDS } from '../eye-styles';
import { activeFrameSubscribers } from '../rig/scheduler';
import { companionBodyAsset } from '@/components/spirit/companion-catalogue';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

beforeEach(() => installSpiritBrowser());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('anatomical body volume preserves the native face and frozen portraits', () => {
  it('keeps both stopped Smiley previews on their bake without a canvas', () => {
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext');
    const view = render(
      <EyesFace
        styleId="smiley"
        variant="male"
        expression="neutral"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
      />
    );
    for (const variant of ['male', 'female'] as const) {
      view.rerender(
        <EyesFace
          styleId="smiley"
          variant={variant}
          expression="neutral"
          gaze={null}
          size="sm"
          life={false}
          animate={false}
        />
      );
      expect(view.container.querySelector('.lia-eyes')).toHaveAttribute('data-motion', 'off');
      expect(view.container.querySelector('canvas')).toBeNull();
      expect(getContext).not.toHaveBeenCalled();
      expect(activeFrameSubscribers()).toBe(0);
    }
  });

  it.each(['reduced', 'hidden'] as const)(
    'retains the body bake before any GPU allocation when %s',
    mode => {
      const browser = installSpiritBrowser(mode === 'reduced');
      if (mode === 'hidden') browser.setVisibility('hidden');
      vi.spyOn(document, 'hidden', 'get').mockImplementation(
        () => document.visibilityState === 'hidden'
      );
      vi.stubGlobal('WebGLRenderingContext', class {});
      const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
      vi.useFakeTimers();
      const { container } = render(
        <EyesFace
          styleId="oscar"
          variant="female"
          expression="sad"
          gaze={null}
          size="sm"
          life={false}
          animate
        />
      );
      act(() => vi.advanceTimersByTime(80));
      expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-volume-ready', 'false');
      expect(container.querySelector('[data-character]')).toHaveStyle({
        '--spirit-body-url': `url('${companionBodyAsset('oscar', 'female')}')`,
      });
      expect(getContext).not.toHaveBeenCalled();
      expect(activeFrameSubscribers()).toBe(0);
    }
  );

  it.each(HYBRID_EYE_STYLE_IDS)(
    'retains both %s identities without allocating a frozen GPU',
    character => {
      const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext');
      const view = render(
        <EyesFace
          styleId={character}
          variant="male"
          expression="sad"
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
            styleId={character}
            variant={variant}
            expression="sad"
            gaze={null}
            size="sm"
            life={false}
            animate={false}
            staticPose
          />
        );
        const body = view.container.querySelector('[data-character]');
        const face = view.container.querySelector('.lia-eyes');
        expect(body).toHaveAttribute('data-spirit-companion', variant);
        expect(body).toHaveStyle({
          '--spirit-body-url': `url('${companionBodyAsset(character, variant)}')`,
        });
        expect(face).toHaveAttribute('data-volume-character', character);
        expect(face).toHaveAttribute('data-volume-variant', variant);
        expect(face).toHaveAttribute('data-volume-ready', 'false');
        expect(face).toHaveAttribute('data-expression', 'sad');
        expect(face).toHaveAttribute('data-motion', 'off');
        expect(view.container.querySelectorAll('[data-volume-surface="left"]')).toHaveLength(2);
        expect(view.container.querySelectorAll('[data-volume-surface="right"]')).toHaveLength(2);
        expect(view.container.querySelectorAll('[data-volume-surface="mouth"]')).toHaveLength(1);
        for (const eye of view.container.querySelectorAll('.lia-eye-shape')) {
          expect(eye.closest('.lia-raster-face-mask')).not.toBeNull();
          expect(eye.querySelector('.lia-eye-pupil')?.parentElement).toHaveClass(
            'lia-eye-pupil-clip'
          );
        }
        const mouth = view.container.querySelector('[data-rig-mouth]');
        expect(mouth?.closest('[data-volume-surface]')).toHaveAttribute(
          'data-volume-surface',
          'mouth'
        );
        expect(mouth?.getAttribute('d')).toBeTruthy();
        expect(
          view.container.querySelector('[data-rig-brow]')?.closest('.lia-raster-face-mask')
        ).toBeNull();
        expect(view.container.querySelectorAll('canvas, img')).toHaveLength(0);
        expect(activeFrameSubscribers()).toBe(0);
      }
      expect(getContext).not.toHaveBeenCalled();
    }
  );

  it.each(['oscar', 'cozmo'] as const)(
    'keeps a stopped %s preview on its existing bake',
    styleId => {
      const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext');
      const { container } = render(
        <EyesFace
          styleId={styleId}
          variant="female"
          expression="neutral"
          gaze={null}
          size="sm"
          life={false}
          animate={false}
        />
      );
      const face = container.querySelector('.lia-eyes');
      expect(face).toHaveAttribute(
        'data-volume-character',
        styleId === 'cozmo' ? 'monitor' : styleId
      );
      expect(face).toHaveAttribute('data-volume-ready', 'false');
      expect(face).toHaveAttribute('data-motion', 'off');
      expect(container.querySelector('canvas')).toBeNull();
      expect(getContext).not.toHaveBeenCalled();
      expect(activeFrameSubscribers()).toBe(0);
    }
  );
});

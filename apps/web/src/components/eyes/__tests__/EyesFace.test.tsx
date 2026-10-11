import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { EyesFace } from '../EyesFace';
import { EYE_EXPRESSIONS } from '../expression-engine';
import { HYBRID_EYE_STYLE_IDS, RIG_EYE_STYLE_IDS } from '../eye-styles';
import { activeFrameSubscribers } from '../rig/scheduler';
import { companionBodyAsset } from '@/components/spirit/companion-catalogue';
import {
  installSpiritBrowser,
  SpiritIntersectionObserver,
} from '@/components/spirit/__tests__/browser';

let clock = 0;
let frameId = 0;
const frames = new Map<number, FrameRequestCallback>();

function advanceFrames(duration = 400) {
  act(() => {
    for (let elapsed = 0; elapsed < duration; elapsed += 16) {
      clock += 16;
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach(frame => frame(clock));
    }
  });
}

function rigRoot(container: HTMLElement) {
  const root = container.querySelector<HTMLElement>('.lia-eyes');
  if (!root) throw new Error('The companion must mount the actual procedural face');
  return root;
}

beforeEach(() => {
  installSpiritBrowser();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
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

describe('EyesFace hybrid companion boundary', () => {
  it.each([
    ['moss', 'female'],
    ['moss', 'male'],
    ['lumen', 'female'],
    ['lumen', 'male'],
    ['nimbo', 'female'],
    ['nimbo', 'male'],
    ['orbit', 'female'],
    ['orbit', 'male'],
    ['bip', 'female'],
    ['bip', 'male'],
    ['boulon', 'female'],
    ['boulon', 'male'],
    ['oscar', 'female'],
    ['oscar', 'male'],
  ] as const)(
    'dispatches %s/%s to its original body and its single native facial rig',
    (character, variant) => {
      const { container, rerender } = render(
        <EyesFace
          styleId={character}
          variant={variant}
          expression="neutral"
          gaze={null}
          size="sm"
          life={false}
          animate={false}
        />
      );
      const companion = container.querySelector('[data-character]');
      expect(companion).toHaveAttribute('data-character', character);
      expect(companion).toHaveAttribute('data-style', character);
      expect(companion).toHaveAttribute('data-spirit-companion', variant);
      expect(companion).toHaveStyle({
        '--spirit-body-url': `url('${companionBodyAsset(character, variant)}')`,
      });
      expect(rigRoot(container)).toHaveAttribute('data-style', 'billes');
      expect(rigRoot(container)).toHaveAttribute('data-expression', 'neutral');
      expect(container.querySelectorAll('.lia-eye-pupil-clip > .lia-eye-pupil')).toHaveLength(2);
      expect(container.querySelector('.lia-monitor-screen')).toBeNull();
      expect(container.querySelector('canvas')).toBeNull();
      expect(container.querySelector('.lia-raster-face-mask [data-rig-mouth]')).toBeInTheDocument();
      expect(activeFrameSubscribers()).toBe(0);
      rerender(
        <EyesFace
          styleId={character}
          variant={variant}
          expression="speaking"
          gaze={{ x: 0.8, y: -0.4 }}
          size="sm"
          life={false}
          animate
        />
      );
      advanceFrames(320);
      expect(rigRoot(container)).toHaveAttribute('data-expression', 'speaking');
      expect(rigRoot(container)).toHaveAttribute('data-gaze-x', '0.8');
      expect(activeFrameSubscribers()).toBe(1);
    }
  );

  it.each(RIG_EYE_STYLE_IDS.filter(style => style !== 'smiley'))(
    'composes %s on the actual monitor while retaining the native face',
    styleId => {
      const { container } = render(
        <EyesFace
          styleId={styleId}
          variant="female"
          expression="speaking"
          gaze={{ x: 0.4, y: -0.2 }}
          size="sm"
          life={false}
        />
      );
      expect(container.querySelector('.lia-monitor')).toBeInTheDocument();
      expect(container.querySelector('.lia-monitor-screen')).toBeInTheDocument();
      expect(container.querySelector('.lia-monitor-screen [data-rig-mouth]')).toBeInTheDocument();
      expect(container.querySelectorAll('.lia-monitor-brows [data-rig-brow]')).toHaveLength(2);
      expect(rigRoot(container)).toHaveAttribute('data-expression', 'speaking');
      expect(rigRoot(container)).toHaveAttribute('data-gaze-x', '0.4');
      expect(activeFrameSubscribers()).toBe(1);
    }
  );
  it.each(EYE_EXPRESSIONS)(
    'renders the real native %s organs on the original 3D body',
    expression => {
      const { container } = render(
        <EyesFace styleId="spirit" variant="female" expression={expression} gaze={null} size="sm" />
      );
      expect(container.querySelector('[data-spirit-companion="female"]')).toBeInTheDocument();
      expect(rigRoot(container)).toHaveAttribute('data-style', 'billes');
      expect(rigRoot(container)).toHaveAttribute('data-expression', expression);
      expect(container.querySelectorAll('.lia-eye-shape')).toHaveLength(2);
      expect(container.querySelectorAll('.lia-eye-pupil-clip > .lia-eye-pupil')).toHaveLength(2);
      expect(container.querySelector('.lia-raster-face-mask [data-rig-mouth]')).toBeInTheDocument();
      expect(container.querySelectorAll('.lia-raster-brows [data-rig-brow]')).toHaveLength(2);
      expect(container.querySelector('[data-rig-mouth]')).toBeInTheDocument();
      expect(container.querySelectorAll('img')).toHaveLength(0);
      expect(activeFrameSubscribers()).toBe(1);
    }
  );

  it.each(['sm', 'md', 'lg', 'xl'] as const)('keeps the %s preset and masculine body', size => {
    const { container } = render(
      <EyesFace
        styleId="spirit"
        variant="male"
        expression="thinking"
        gaze={null}
        size={size}
        animate={false}
      />
    );
    expect(container.querySelector('[data-spirit-companion="male"]')).toBeInTheDocument();
    expect(rigRoot(container)).toHaveClass(`lia-eyes--${size}`);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it.each([...RIG_EYE_STYLE_IDS, ...HYBRID_EYE_STYLE_IDS])(
    'keeps both %s identities in the extra-large preset through the renderer boundary',
    styleId => {
      const { container, rerender } = render(
        <EyesFace
          styleId={styleId}
          variant="female"
          expression="joy"
          gaze={null}
          size="xl"
          life={false}
          animate={false}
          staticPose
        />
      );
      expect(rigRoot(container)).toHaveClass('lia-eyes--xl');
      expect(rigRoot(container)).toHaveAttribute('data-expression', 'joy');
      expect(container.querySelector('canvas')).toBeNull();
      expect(activeFrameSubscribers()).toBe(0);
      rerender(
        <EyesFace
          styleId={styleId}
          variant="male"
          expression="joy"
          gaze={null}
          size="xl"
          life={false}
          animate={false}
          staticPose
        />
      );
      expect(rigRoot(container)).toHaveClass('lia-eyes--xl');
      if (styleId === 'smiley')
        expect(rigRoot(container)).toHaveAttribute('data-smiley-variant', 'male');
      if (HYBRID_EYE_STYLE_IDS.some(character => character === styleId)) {
        expect(container.querySelector(`[data-character="${styleId}"]`)).toHaveAttribute(
          'data-spirit-companion',
          'male'
        );
      }
      expect(activeFrameSubscribers()).toBe(0);
    }
  );

  it('projects gaze and the genuine native blink onto separate eye channels', () => {
    const { container, rerender } = render(
      <EyesFace styleId="spirit" variant="male" expression="neutral" gaze={null} size="sm" />
    );
    const root = rigRoot(container);
    rerender(
      <EyesFace
        styleId="spirit"
        variant="male"
        expression="neutral"
        gaze={{ x: 0.8, y: -0.4 }}
        gazeDurationMs={120}
        blinking
        size="sm"
      />
    );
    advanceFrames(112);
    expect(Number.parseFloat(root.style.getPropertyValue('--rig-blink-l'))).toBeGreaterThan(0.5);
    expect(Number.parseFloat(root.style.getPropertyValue('--rig-gaze-x'))).toBeGreaterThan(0);
    advanceFrames(500);
    expect(Number.parseFloat(root.style.getPropertyValue('--rig-blink-l'))).toBeLessThan(0.1);
    expect(root.style.getPropertyValue('--rig-gaze-x')).not.toBe('0');
  });

  it('keeps native mouth speech, gestures, emotes and one-shot accessories', () => {
    const { container, rerender } = render(
      <EyesFace
        styleId="spirit"
        variant="female"
        expression="neutral"
        gaze={null}
        size="sm"
        life={false}
      />
    );
    const root = rigRoot(container);
    const mouth = container.querySelector('[data-rig-mouth]');
    const neutral = mouth?.getAttribute('d');
    rerender(
      <EyesFace
        styleId="spirit"
        variant="female"
        expression="speaking"
        gaze={null}
        size="sm"
        life={false}
        gesture="bounce"
        emote="!"
        emoteLeaving
        accessory="sparkle"
        idleFamily="lively"
        emphasis={1.2}
        responseWeight={0.7}
      />
    );
    advanceFrames(320);
    expect(mouth?.getAttribute('d')).not.toBe(neutral);
    expect(root).toHaveAttribute('data-family', 'lively');
    expect(root).toHaveAttribute('data-gesture', 'bounce');
    expect(container.querySelector('.lia-emote')).toHaveTextContent('!');
    expect(container.querySelector('.lia-emote')).toHaveClass('is-leaving');
    expect(container.querySelector('.lia-accessory')).toHaveAttribute('data-accessory', 'sparkle');
    const speaking = mouth?.getAttribute('d');
    advanceFrames(320);
    expect(mouth?.getAttribute('d')).not.toBe(speaking);
    expect(activeFrameSubscribers()).toBe(1);
  });

  it.each(HYBRID_EYE_STYLE_IDS)(
    'uses the single %s native visibility owner and honors tab and reduced-motion changes',
    styleId => {
      const browser = installSpiritBrowser();
      const { container, rerender } = render(
        <EyesFace styleId={styleId} variant="female" expression="thinking" gaze={null} size="sm" />
      );
      const root = rigRoot(container);
      expect(SpiritIntersectionObserver.instances).toHaveLength(1);
      const observer = SpiritIntersectionObserver.instances[0];
      act(() => observer.notify(root, false));
      expect(activeFrameSubscribers()).toBe(0);
      rerender(
        <EyesFace styleId={styleId} variant="female" expression="joy" gaze={null} size="sm" />
      );
      expect(activeFrameSubscribers()).toBe(0);
      act(() => observer.notify(root, true));
      expect(activeFrameSubscribers()).toBe(1);
      const hidden = vi.spyOn(document, 'hidden', 'get');
      hidden.mockReturnValue(true);
      act(() => browser.setVisibility('hidden'));
      expect(activeFrameSubscribers()).toBe(0);
      hidden.mockReturnValue(false);
      act(() => browser.setVisibility('visible'));
      expect(activeFrameSubscribers()).toBe(1);
      act(() => browser.setMotion(true));
      advanceFrames();
      expect(activeFrameSubscribers()).toBe(0);
      act(() => browser.setMotion(false));
      expect(activeFrameSubscribers()).toBe(1);
    }
  );

  it('static previews have no frame subscription and wake only when requested', () => {
    const { container, rerender } = render(
      <EyesFace
        styleId="spirit"
        variant="female"
        expression="joy"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
      />
    );
    expect(activeFrameSubscribers()).toBe(0);
    expect(rigRoot(container)).toHaveAttribute('data-life', 'off');
    rerender(
      <EyesFace
        styleId="spirit"
        variant="female"
        expression="joy"
        gaze={null}
        size="sm"
        life={false}
        animate
      />
    );
    expect(activeFrameSubscribers()).toBe(1);
    rerender(
      <EyesFace
        styleId="spirit"
        variant="male"
        expression="fear"
        gaze={null}
        size="sm"
        life={false}
        animate={false}
      />
    );
    expect(activeFrameSubscribers()).toBe(0);
    expect(rigRoot(container)).toHaveAttribute('data-expression', 'fear');
    expect(container.querySelectorAll('.lia-eyes')).toHaveLength(1);
  });

  it.each(['female', 'male'] as const)(
    'keeps %s Smiley on its native renderer with its original body and iris boundaries',
    variant => {
      const { container } = render(
        <EyesFace styleId="smiley" variant={variant} expression="joy" gaze={null} size="sm" />
      );
      expect(rigRoot(container)).toHaveAttribute('data-smiley-variant', variant);
      expect(container.querySelectorAll('.lia-eye-shape')).toHaveLength(2);
      expect(container.querySelectorAll('.lia-eye-blink')).toHaveLength(2);
      expect(container.querySelector('[data-spirit-companion]')).toBeNull();
      expect(container.querySelectorAll('.lia-eye-pupil-clip > .lia-eye-pupil')).toHaveLength(2);
      const boundary = container.querySelector('.lia-raster-face-mask');
      expect(boundary?.querySelectorAll('.lia-eye-shape')).toHaveLength(2);
      expect(boundary?.querySelector('[data-rig-mouth]')).not.toBeNull();
      expect(boundary?.querySelector('[data-rig-brow]')).toBeNull();
      expect(activeFrameSubscribers()).toBe(1);
    }
  );
});

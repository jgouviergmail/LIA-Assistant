import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { EyesWidget } from '../EyesWidget';
import { MASK_APPLY_DELAY_MS, MIN_EXPRESSION_HOLD_MS } from '../expression-engine';
import { activeFrameSubscribers } from '../rig/scheduler';
import { HYBRID_EYE_STYLE_IDS } from '../eye-styles';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

// The environment acquisition has its own HTTP lifecycle tests. The behavior,
// expression engine, cookie preference, renderer and widget controls remain real.
vi.mock('../useCompanionEnvironment', () => ({ useCompanionEnvironment: vi.fn() }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-08-20T14:00:00'));
  localStorage.clear();
  document.cookie = 'lia_gender=male; path=/';
  useEyesWidgetStore.getState().reset();
  useEyesWidgetStore.getState().setStyle('spirit');
  // Size-cycle behavior starts from responsive auto rather than depending
  // on the application's explicit XL default.
  useEyesWidgetStore.getState().setSize('auto');
  useEyesSignalsStore.getState().reset();
  usePsycheStore.getState().reset();
  useVoiceModeStore.getState().reset();
  useVoiceModeStore.setState({ isEnabled: false, state: 'idle' });
  installSpiritBrowser();
});

afterEach(() => {
  cleanup();
  document.cookie = 'lia_gender=female; path=/';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function settleExpression(): void {
  act(() => vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 5));
}

describe('EyesWidget with the spirit renderer', () => {
  it('hands cursor gaze to the same native facial rig', () => {
    const media = window.matchMedia('(hover: hover) and (pointer: fine)');
    vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
      ...media,
      media: query,
      matches: query.includes('pointer: fine'),
    }));
    useEyesWidgetStore.getState().setPosition({ xPct: 40, yPct: 30 });
    const frames = vi.spyOn(window, 'requestAnimationFrame');
    render(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    const initialFrames = frames.mock.calls.length;
    fireEvent.pointerMove(window, { clientX: 100, clientY: 100 });
    expect(frames.mock.calls.length).toBeGreaterThan(initialFrames);
  });

  it('uses the existing gender preference and the actual streaming expression on one native rig', () => {
    const { container, rerender } = render(
      <EyesWidget chatStatus="streaming" streamPhase="progress" hitlAwaiting={false} />
    );
    settleExpression();
    expect(container.querySelector('[data-spirit-companion]')).toHaveAttribute(
      'data-spirit-companion',
      'male'
    );
    expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-expression', 'thinking');
    expect(activeFrameSubscribers()).toBe(1);
    rerender(<EyesWidget chatStatus="streaming" streamPhase="answer" hitlAwaiting={false} />);
    settleExpression();
    expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-expression', 'attentive');
  });

  it.each(HYBRID_EYE_STYLE_IDS)(
    'updates the %s variant from the existing preference change event',
    styleId => {
      useEyesWidgetStore.getState().setStyle(styleId);
      const { container } = render(
        <EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />
      );
      expect(container.querySelector('[data-character]')).toHaveAttribute(
        'data-character',
        styleId
      );
      act(() => {
        document.cookie = 'lia_gender=female; path=/';
        window.dispatchEvent(new Event('lia-gender-change'));
      });
      expect(container.querySelector('[data-spirit-companion]')).toHaveAttribute(
        'data-spirit-companion',
        'female'
      );
    }
  );

  it.each(HYBRID_EYE_STYLE_IDS)(
    'preserves %s size, keyboard movement, and the hide/restore round trip',
    styleId => {
      useEyesWidgetStore.getState().setStyle(styleId);
      useEyesWidgetStore.getState().setPosition({ xPct: 40, yPct: 30 });
      useEyesWidgetStore.getState().setLandingPosition({ xPct: 20, yPct: 15 });
      const { container } = render(
        <EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />
      );
      expect(container.querySelector('.lia-eyes')).toHaveClass('lia-eyes--sm');
      fireEvent.click(screen.getByRole('button', { name: 'eyes.cycle_size' }));
      expect(container.querySelector('.lia-eyes')).toHaveClass('lia-eyes--md');
      fireEvent.keyDown(screen.getByRole('group'), { key: 'ArrowLeft' });
      expect(useEyesWidgetStore.getState().position?.xPct).toBeLessThan(40);
      expect(useEyesWidgetStore.getState().landingPosition).toEqual({ xPct: 20, yPct: 15 });
      fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
      expect(container.querySelector('.lia-eyes')).toBeNull();
      expect(activeFrameSubscribers()).toBe(0);
      fireEvent.click(screen.getByRole('button', { name: 'eyes.restore' }));
      expect(container.querySelector('.lia-eyes')).toHaveClass('lia-eyes--md');
      expect(useEyesWidgetStore.getState().style).toBe(styleId);
      expect(container.querySelector('[data-character]')).toHaveAttribute(
        'data-character',
        styleId
      );
      expect(activeFrameSubscribers()).toBe(1);
    }
  );

  it('forces landing Bip male XL over a saved Mousse female medium preference without changing that preference or showing a size cycle', () => {
    document.cookie = 'lia_gender=female; path=/';
    useEyesWidgetStore.getState().setStyle('moss');
    useEyesWidgetStore.getState().setSize('md');
    const saved = localStorage.getItem(EYES_WIDGET_PREFS_KEY),
      cookie = document.cookie;
    const { container, rerender } = render(
      <EyesWidget
        surface="landing"
        styleId="bip"
        size="xl"
        variant="male"
        chatStatus="idle"
        streamPhase="answer"
        hitlAwaiting={false}
      />
    );
    expect(container.querySelector('[data-character]')).toHaveAttribute('data-character', 'bip');
    expect(container.querySelector('[data-spirit-companion]')).toHaveAttribute(
      'data-spirit-companion',
      'male'
    );
    expect(container.querySelector('.lia-eyes')).toHaveClass('lia-eyes--xl');
    expect(screen.queryByRole('button', { name: 'eyes.cycle_size' })).not.toBeInTheDocument();
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toBe(saved);
    expect(document.cookie).toBe(cookie);
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    expect(container.querySelector('[data-character]')).toHaveAttribute('data-character', 'moss');
    expect(container.querySelector('[data-spirit-companion]')).toHaveAttribute(
      'data-spirit-companion',
      'female'
    );
    expect(container.querySelector('.lia-eyes')).toHaveClass('lia-eyes--md');
    expect(screen.getByRole('button', { name: 'eyes.cycle_size' })).toBeInTheDocument();
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toBe(saved);
    expect(document.cookie).toBe(cookie);
  });

  it('keeps the selected Smiley style while changing its identity from the shared gender preference', () => {
    useEyesWidgetStore.getState().setStyle('smiley');
    const { container } = render(
      <EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />
    );
    const face = container.querySelector('.lia-eyes');
    expect(face).toHaveAttribute('data-smiley-variant', 'male');
    const mouth = container.querySelector('[data-rig-mouth]');
    act(() => {
      document.cookie = 'lia_gender=female; path=/';
      window.dispatchEvent(new Event('lia-gender-change'));
    });
    expect(container.querySelector('.lia-eyes')).toBe(face);
    expect(face).toHaveAttribute('data-smiley-variant', 'female');
    expect(container.querySelector('[data-rig-mouth]')).toBe(mouth);
    expect(useEyesWidgetStore.getState().style).toBe('smiley');
    expect(activeFrameSubscribers()).toBe(1);
  });
});

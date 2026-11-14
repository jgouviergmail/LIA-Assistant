/**
 * EyesWidget — floating shell behavior.
 *
 * Covers: accessible chrome (translated names), hide/restore round-trip with
 * persistence, size cycling, keyboard moves, drag commit, the double-click
 * wink one-shot, the expression wiring through useEyesBehavior (status ×
 * phase × signals), the post-error decay and the blink scheduler — all with
 * fake timers and an injected Math.random, never waiting on an animation.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { createInstance } from 'i18next';
import * as reactI18next from 'react-i18next';

import { EyesWidget } from '../EyesWidget';
import { anchoredPosition } from '../useEyesAnchor';
import {
  ACCESSORY_DURATION_MS,
  BLINK_DURATION_MS,
  BLINK_MIN_DELAY_MS,
  EMOTE_EXIT_MS,
  ERROR_HOLD_MS,
  GAZE_RETURN_MS,
  GESTURE_DURATION_MS,
  IDLE_GESTURE_MAX_DELAY_MS,
  IDLE_GESTURE_MIN_DELAY_MS,
  INACTIVITY_ASLEEP_MS,
  INACTIVITY_DROWSY_MS,
  INACTIVITY_SLEEPY_MS,
  MASK_APPLY_DELAY_MS,
  MIN_EXPRESSION_HOLD_MS,
  SHORT_NAP_MS,
  WAKE_SHORT_PERFORMANCE,
  SACCADE_HOLD_MIN_MS,
  SACCADE_MOVE_MS,
  WAKE_PERFORMANCE,
  RETURN_PERK_MIN_AWAY_MS,
  WINK_DURATION_MS,
} from '../expression-engine';
import { HAND_OVER_AFTER_MS } from '../exchange-beats';
import { GAZE_TARGET_REFRESH_MS, gazeTargetProps } from '../gaze-target';
import type { Activity } from '../activity';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import enTranslations from '../../../../locales/en/translation.json';
import frTranslations from '../../../../locales/fr/translation.json';

// This suite owns widget behavior with a neutral environment. Acquisition is
// covered by useCompanionEnvironment.test.tsx and chat-avatar-environment E2E.
// Leaving that HTTP effect live makes its asynchronous failure reset the store
// outside act; the expression engine, stores, rig and timers remain real here.
vi.mock('../useCompanionEnvironment', () => ({ useCompanionEnvironment: vi.fn() }));

function renderWidget(
  props: Partial<Parameters<typeof EyesWidget>[0]> = {}
): ReturnType<typeof render> {
  const result = render(
    <EyesWidget
      {...props}
      chatStatus={props.chatStatus ?? 'idle'}
      streamPhase={props.streamPhase ?? 'answer'}
      hitlAwaiting={props.hitlAwaiting ?? false}
    />
  );
  // The initial expression derivation is scheduled at 0 ms (ratchet-driven
  // design) — flush it so assertions read the derived frame.
  act(() => {
    vi.advanceTimersByTime(1);
  });
  return result;
}

/** Let a masked transition land — the three-beat swaps the face at the top
 * of the lid sweep (MASK_APPLY_DELAY_MS after the change). */
function settleMask(): void {
  act(() => {
    vi.advanceTimersByTime(MASK_APPLY_DELAY_MS + 5);
  });
}

/**
 * Inactivity and sleep duration use Date.now(); rig motion uses the monotone
 * RAF clock. Age the former, then run the real heartbeat (1000ms), holds and
 * transitions. Replaying fifteen minutes of RAF cost 77s in full coverage
 * without adding an oracle: continuous motion has its own rig tests.
 * The clock assertion ensures a wall-time jump never fakes a motion delta.
 */
function observeInactivityAt(wallTime: number): void {
  act(() => {
    const motionTime = performance.now();
    vi.setSystemTime(wallTime);
    expect(performance.now()).toBe(motionTime);
    vi.advanceTimersByTime(1500);
  });
}

/** Observe every real stage instead of jumping directly to the final pose. */
function fallAsleep(): void {
  const mountedAt = Date.now();
  for (const [elapsed, expression] of [
    [INACTIVITY_DROWSY_MS, 'tired'],
    [INACTIVITY_SLEEPY_MS, 'sleepy'],
    [INACTIVITY_ASLEEP_MS, 'sleep'],
  ] as const) {
    observeInactivityAt(mountedAt + elapsed);
    expect(eyesRoot().dataset.expression).toBe(expression);
  }
}

/** What `matchMedia` answers a person who asked for less motion: a whole
 * `MediaQueryList`, built rather than asserted into shape. */
function reducedMotionQuery(query: string): MediaQueryList {
  const events = new EventTarget();
  return {
    matches: query.includes('prefers-reduced-motion'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events),
  };
}

function eyesRoot(): HTMLElement {
  const root = document.querySelector('.lia-eyes');
  if (!(root instanceof HTMLElement)) throw new Error('eyes not rendered');
  return root;
}

beforeEach(() => {
  vi.useFakeTimers();
  // Pin the clock mid-afternoon: the idle expression depends on the local
  // hour (night → sleepy), so an unpinned clock would make these assertions
  // flip depending on WHEN the suite runs.
  vi.setSystemTime(new Date('2026-08-20T14:00:00'));
  localStorage.removeItem(EYES_WIDGET_PREFS_KEY);
  useEyesWidgetStore.getState().reset();
  // This suite exercises a native look and responsive sizing, independently
  // of the application's chosen default character and explicit XL preset.
  useEyesWidgetStore.getState().setStyle('cozmo');
  useEyesWidgetStore.getState().setSize('auto');
  useEyesSignalsStore.getState().reset();
  usePsycheStore.getState().reset();
  useCompanionEnvironmentStore.getState().reset();
  useVoiceModeStore.getState().reset();
  useVoiceModeStore.setState({ isEnabled: false, state: 'idle' });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  // `matchMedia` is a mock the setup file installs, not a spy: restoring the
  // spies leaves a preference a test overrode (reduced motion) in force for
  // every test after it — which then passes or fails by its place in the file.
  vi.mocked(window.matchMedia).mockReset();
});

describe('EyesWidget — chrome & preferences', () => {
  it('keeps keyboard focus and movement available when no pointer-safe frame exists', async () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    vi.spyOn(group, 'getBoundingClientRect').mockReturnValue(new DOMRect(10, 100, 200, 180));
    const input = document.createElement('input');
    input.getBoundingClientRect = () => new DOMRect(0, 0, innerWidth, innerHeight);
    document.body.append(input);
    group.focus();
    window.dispatchEvent(new Event('resize'));
    await act(() => vi.advanceTimersByTimeAsync(200));
    expect(group).toHaveStyle({ pointerEvents: 'none' });
    expect(eyesRoot()).toBeVisible();
    expect(group).toHaveFocus();
    expect(group.tabIndex).toBe(0);
    fireEvent.keyDown(group, { key: 'ArrowRight' });
    expect(useEyesWidgetStore.getState().position).not.toBeNull();
    expect(group).toHaveFocus();
    input.remove();
  });

  describe('on a phone the person alone places the companion (owner, 2026-10-17)', () => {
    function onPhone(): void {
      const media = window.matchMedia('');
      vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
        ...media,
        media: query,
        matches: query === '(max-width: 1023px)',
      }));
    }

    /** A control and a heading under the companion, then a scroll and a resize. */
    async function coverAndScroll(group: HTMLElement): Promise<void> {
      vi.spyOn(group, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 150, 200, 180));
      const heading = document.createElement('h1');
      heading.getBoundingClientRect = () => new DOMRect(0, 100, innerWidth, 100);
      const control = document.createElement('button');
      control.getBoundingClientRect = () => new DOMRect(0, 200, innerWidth, 60);
      document.body.append(heading, control);
      window.dispatchEvent(new Event('scroll'));
      window.dispatchEvent(new Event('resize'));
      await act(() => vi.advanceTimersByTimeAsync(400));
    }

    it('keeps the whole face on its saved spot outside the chat, whatever scrolls under it', async () => {
      onPhone();
      const saved = { xPct: 10, yPct: 20 };
      useEyesWidgetStore.getState().setPosition(saved);
      renderWidget({ dockToChat: false });
      const group = screen.getByRole('group', { name: 'eyes.widget_label' });
      await coverAndScroll(group);
      expect(group.style.left).toBe(`${(saved.xPct / 100) * innerWidth}px`);
      expect(group.style.top).toBe(`${(saved.yPct / 100) * innerHeight}px`);
      expect(group.style.pointerEvents).toBe('');
      expect(eyesRoot()).toBeVisible();
      expect(useEyesWidgetStore.getState().position).toEqual(saved);
    });

    it('keeps its default corner when the person never moved it', async () => {
      onPhone();
      renderWidget({ dockToChat: false });
      const group = screen.getByRole('group', { name: 'eyes.widget_label' });
      await coverAndScroll(group);
      expect(group.style.left).toBe('');
      expect(group.style.top).toBe('');
      expect(group).toHaveClass('bottom-32', 'right-6');
      expect(eyesRoot()).toBeVisible();
    });
  });

  it('renders a focusable group with a translated name and the two eyes', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    expect(group.tabIndex).toBe(0);
    expect(document.querySelectorAll('.lia-eye-shape')).toHaveLength(2);
    expect(document.querySelectorAll('.lia-eye-blink')).toHaveLength(2);
  });

  it('hide → restore dot → show again, with the preference persisted', () => {
    renderWidget();
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    expect(document.querySelector('.lia-eyes')).toBeNull();
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toContain('"visible":false');

    fireEvent.click(screen.getByRole('button', { name: 'eyes.restore' }));
    expect(document.querySelector('.lia-eyes')).not.toBeNull();
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toContain('"visible":true');
  });

  it('auto size resolves small without desktop hover, cycling picks explicit presets', () => {
    renderWidget();
    // Global matchMedia mock answers false → not desktop → auto resolves sm.
    expect(eyesRoot().classList.contains('lia-eyes--sm')).toBe(true);
    const button = screen.getByRole('button', { name: 'eyes.cycle_size' });
    for (const size of ['md', 'lg', 'xl', 'sm', 'md'] as const) {
      fireEvent.click(button);
      expect(eyesRoot()).toHaveClass(`lia-eyes--${size}`);
      expect(useEyesWidgetStore.getState().size).toBe(size);
      expect(button).toHaveAttribute('title', `eyes.sizes.${size}`);
    }
  });

  it('anchoredPosition clamp priority: clearing the delete button outranks centering', () => {
    const rect = (r: Partial<DOMRect>): DOMRect =>
      ({ x: 0, y: 0, toJSON: () => ({}), ...r }) as DOMRect;
    const start = rect({ left: 300, right: 400, top: 100, bottom: 140 });
    const end = rect({ left: 460, right: 580, top: 100, bottom: 140 });
    // Gap (400..460) is narrower than the 120 px widget: the widget yields
    // leftward so its right edge stays 8 px clear of the delete button.
    const pos = anchoredPosition(start, end, { w: 120, h: 50 });
    expect(pos.left).toBe(460 - 8 - 120);
    expect(pos.top).toBe(95);
  });

  it('docks between the FIRST VISIBLE search form and the RAG badge', () => {
    const rect = (r: Partial<DOMRect>): DOMRect =>
      ({ x: 0, y: 0, toJSON: () => ({}), ...r }) as DOMRect;
    // Responsive twin of the search control, hidden at this breakpoint
    // (0×0 rect) — the dock must skip it for the visible form.
    const hiddenStart = document.createElement('button');
    hiddenStart.setAttribute('data-eyes-anchor-start', '');
    const start = document.createElement('div');
    start.setAttribute('data-eyes-anchor-start', '');
    const end = document.createElement('span');
    end.setAttribute('data-eyes-anchor-end', '');
    document.body.append(hiddenStart, start, end);
    vi.spyOn(start, 'getBoundingClientRect').mockReturnValue(
      rect({
        left: 300,
        right: 400,
        top: 100,
        bottom: 140,
        width: 100,
        height: 40,
      })
    );
    vi.spyOn(end, 'getBoundingClientRect').mockReturnValue(
      rect({
        left: 700,
        right: 820,
        top: 100,
        bottom: 140,
        width: 120,
        height: 40,
      })
    );
    try {
      renderWidget();
      act(() => {
        vi.advanceTimersByTime(30); // flush the rAF-scheduled measure
      });
      const group = screen.getByRole('group', { name: 'eyes.widget_label' });
      // Widget rect is 0×0 in jsdom → left = horizontal midpoint of the gap
      // (400..700 → 550), top = shared row center (120).
      expect(group.style.left).toBe('550px');
      expect(group.style.top).toBe('120px');
    } finally {
      hiddenStart.remove();
      start.remove();
      end.remove();
    }
  });

  it('arrow keys move the widget and persist a clamped position', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    fireEvent.keyDown(group, { key: 'ArrowLeft' });
    const pos = useEyesWidgetStore.getState().position;
    expect(pos).not.toBeNull();
    expect(pos!.xPct).toBeGreaterThanOrEqual(0);
    expect(pos!.yPct).toBeGreaterThanOrEqual(0);
  });

  it('disabling the chat dock immediately drops its previous position and stops landmark measurements', () => {
    const start = document.createElement('div'),
      end = document.createElement('span');
    start.dataset.eyesAnchorStart = '';
    end.dataset.eyesAnchorEnd = '';
    document.body.append(start, end);
    const readStart = vi
        .spyOn(start, 'getBoundingClientRect')
        .mockReturnValue(new DOMRect(300, 100, 100, 40)),
      readEnd = vi
        .spyOn(end, 'getBoundingClientRect')
        .mockReturnValue(new DOMRect(700, 100, 120, 40));
    const { rerender, unmount } = renderWidget();
    try {
      act(() => vi.advanceTimersByTime(30));
      const group = screen.getByRole('group', { name: 'eyes.widget_label' });
      expect(group.style.left).toBe('550px');
      expect(group.style.top).toBe('120px');
      readStart.mockClear();
      readEnd.mockClear();
      rerender(
        <EyesWidget
          chatStatus="idle"
          streamPhase="answer"
          hitlAwaiting={false}
          dockToChat={false}
        />
      );
      expect(group.style.left).toBe('');
      expect(group.style.top).toBe('');
      expect(group).toHaveClass('bottom-32', 'right-6');
      fireEvent(window, new Event('resize'));
      act(() => vi.advanceTimersByTime(1500));
      expect(readStart).not.toHaveBeenCalled();
      expect(readEnd).not.toHaveBeenCalled();
      expect(useEyesWidgetStore.getState().position).toBeNull();
    } finally {
      unmount();
      start.remove();
      end.remove();
    }
  });

  it('a drag beyond the threshold commits a position; a micro-move does not', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });

    // Micro-move: stays a click, no position committed.
    fireEvent.pointerDown(group, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(group, { pointerId: 1, clientX: 102, clientY: 101 });
    fireEvent.pointerUp(group, { pointerId: 1, clientX: 102, clientY: 101 });
    expect(useEyesWidgetStore.getState().position).toBeNull();

    // Real drag: commits.
    fireEvent.pointerDown(group, { pointerId: 2, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(group, { pointerId: 2, clientX: 160, clientY: 140 });
    fireEvent.pointerUp(group, { pointerId: 2, clientX: 160, clientY: 140 });
    expect(useEyesWidgetStore.getState().position).not.toBeNull();
  });
});

describe('EyesWidget — the landing surface', () => {
  it.each([14, 23, 3])('keeps BIP awake at %i h through every inactivity stage', hour => {
    const now = new Date('2026-08-20T14:00:00');
    now.setHours(hour);
    vi.setSystemTime(now);
    renderWidget({ surface: 'landing', styleId: 'bip', size: 'xl', variant: 'male' });
    const mountedAt = Date.now();
    for (const elapsed of [
      0,
      INACTIVITY_DROWSY_MS,
      INACTIVITY_SLEEPY_MS,
      INACTIVITY_ASLEEP_MS,
      24 * 60 * 60 * 1000,
    ]) {
      observeInactivityAt(mountedAt + elapsed);
      expect(eyesRoot().dataset.expression).toBe('neutral');
      expect(document.querySelector('.lia-emote')?.textContent).not.toBe('z');
    }
  });

  function renderOnLanding(): ReturnType<typeof render> {
    const result = render(
      <EyesWidget surface="landing" chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />
    );
    act(() => {
      vi.advanceTimersByTime(1);
    });
    return result;
  }

  it('rests in the bottom-right corner, fixed to the viewport, with no dock to measure', () => {
    renderOnLanding();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    expect(group.className).toContain('fixed');
    expect(group.className).toContain('bottom-6');
    expect(group.className).toContain('right-6');
    // No inline dock position: the landing has no header anchors.
    expect(group.style.left).toBe('');
    expect(group.style.top).toBe('');
  });

  it('writes a drag to the LANDING slot and leaves the chat slot untouched', () => {
    renderOnLanding();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    fireEvent.pointerDown(group, { pointerId: 9, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(group, { pointerId: 9, clientX: 170, clientY: 150 });
    fireEvent.pointerUp(group, { pointerId: 9, clientX: 170, clientY: 150 });
    expect(useEyesWidgetStore.getState().landingPosition).not.toBeNull();
    expect(useEyesWidgetStore.getState().position).toBeNull();
    // ...and the widget now sits at that percentage, still fixed.
    expect(parseFloat(group.style.left)).toBeCloseTo(
      (window.innerWidth * (useEyesWidgetStore.getState().landingPosition?.xPct ?? 0)) / 100
    );
    expect(group.className).toContain('fixed');
  });

  it('reads the landing slot, not the chat one, when both are stored', () => {
    useEyesWidgetStore.getState().setPosition({ xPct: 10, yPct: 20 });
    useEyesWidgetStore.getState().setLandingPosition({ xPct: 70, yPct: 80 });
    renderOnLanding();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    expect(parseFloat(group.style.left)).toBeCloseTo(window.innerWidth * 0.7);
    expect(parseFloat(group.style.top)).toBeCloseTo(window.innerHeight * 0.8);
  });

  it('lets the mount FORCE a look over the persisted preference', () => {
    useEyesWidgetStore.getState().setStyle('billes');
    render(
      <EyesWidget
        surface="landing"
        styleId="capsules"
        chatStatus="idle"
        streamPhase="answer"
        hitlAwaiting={false}
      />
    );
    act(() => {
      vi.advanceTimersByTime(1);
    });
    const eyes = screen
      .getByRole('group', { name: 'eyes.widget_label' })
      .querySelector('.lia-eyes');
    expect(eyes).toHaveAttribute('data-style', 'capsules');
    // The preference itself is untouched: the chat keeps the marbles.
    expect(useEyesWidgetStore.getState().style).toBe('billes');
  });

  it('minimises into the landing corner and restores from it', () => {
    renderOnLanding();
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    const dot = screen.getByRole('button', { name: 'eyes.restore' });
    expect(dot.className).toContain('bottom-6');
    fireEvent.click(dot);
    expect(screen.getByRole('group', { name: 'eyes.widget_label' })).toBeInTheDocument();
  });
});

describe('EyesWidget — accessible names exist in the real locales (en + fr)', () => {
  it.each(['widget_label', 'minimize', 'restore', 'cycle_size'] as const)(
    'eyes.%s is translated and non-empty',
    key => {
      // `eyes` mixes flat strings and the nested `styles` map — index the
      // flat keys only (no contract-bypassing cast on the whole block).
      const en = enTranslations.eyes[key];
      const fr = frTranslations.eyes[key];
      expect(en).toBeTruthy();
      expect(fr).toBeTruthy();
      expect(en).not.toBe(fr);
    }
  );

  it.each(['en', 'fr'] as const)(
    'names the size control and its current preset in %s',
    async locale => {
      const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
      const dictionary = locale === 'en' ? enTranslations : frTranslations;
      const i18n = createInstance();
      await i18n.init({
        lng: locale,
        fallbackLng: locale,
        resources: { [locale]: { translation: dictionary } },
      });
      vi.spyOn(reactI18next, 'useTranslation').mockImplementation(actual.useTranslation);
      render(
        <actual.I18nextProvider i18n={i18n}>
          <EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />
        </actual.I18nextProvider>
      );
      act(() => vi.advanceTimersByTime(1));
      const button = screen.getByRole('button', { name: dictionary.eyes.cycle_size });
      expect(button).toHaveAttribute('title', dictionary.eyes.sizes.sm);
      for (const size of ['md', 'lg', 'xl', 'sm', 'md'] as const) {
        fireEvent.click(button);
        expect(button).toHaveAttribute('title', dictionary.eyes.sizes[size]);
        expect(eyesRoot()).toHaveClass(`lia-eyes--${size}`);
        expect(useEyesWidgetStore.getState().size).toBe(size);
      }
    }
  );
});

describe('EyesWidget — expression wiring', () => {
  it('maps chat status and phase through the engine (progress + tool → searching)', () => {
    act(() => {
      useEyesSignalsStore.getState().recordStep('tool');
    });
    renderWidget({ chatStatus: 'streaming', streamPhase: 'progress' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('searching');
  });

  it('text streaming stays attentive; HITL overrides it with a question', () => {
    const { rerender } = renderWidget({
      chatStatus: 'streaming',
      streamPhase: 'answer',
    });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('attentive');
    rerender(<EyesWidget chatStatus="streaming" streamPhase="answer" hitlAwaiting />);
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('question');
  });

  it('a live store signal re-derives the frame (reaction after done)', () => {
    renderWidget();
    expect(eyesRoot().dataset.expression).toBe('neutral');
    act(() => {
      useEyesSignalsStore.getState().setReaction('excited', Date.now());
    });
    // A reaction is not urgent: the fresh mount frame holds its minimum
    // beat first (anti-zapping), then the masked swap lands the reaction.
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('excited');
  });

  it('voice speaking drives the speaking expression', () => {
    renderWidget();
    act(() => {
      useVoiceModeStore.setState({ state: 'speaking' });
    });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('speaking');
  });

  it('dozes off from mount without any user gesture (progressive sleep)', () => {
    // Pinned for the same reason as the wake-startle test: a free-RNG flicker
    // during the long doze can hold the frame at the assertion instant.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    expect(eyesRoot().dataset.expression).toBe('neutral');
    fallAsleep();
    expect(eyesRoot().dataset.expression).toBe('sleep');
  });

  it('an error is worried, then decays back to idle after the hold', () => {
    renderWidget({ chatStatus: 'error' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('worried');
    act(() => {
      vi.advanceTimersByTime(ERROR_HOLD_MS + 1500);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
  });
});

describe('EyesWidget — idle life (deterministic via mocked RNG)', () => {
  it('wanders the gaze with a saccade jump, holds, then eases back to center', () => {
    // Explicit rng sequence (mount order: blink delay, idle delay; tick
    // order: pick, pre-gaze blink roll, target x, target y, hold).
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0) // pick → saccade
      .mockReturnValueOnce(0.9) // pre-gaze blink roll → no
      .mockReturnValueOnce(0) // target x → -0.35
      .mockReturnValueOnce(0) // target y → -0.22
      .mockReturnValueOnce(0) // hold → SACCADE_HOLD_MIN_MS
      .mockReturnValue(0.9);
    renderWidget();
    expect(eyesRoot().dataset.gazeX).toBe('0');
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.gazeX).toBe('-0.35');
    expect(eyesRoot().dataset.gazeMs).toBe(String(SACCADE_MOVE_MS));
    act(() => {
      vi.advanceTimersByTime(SACCADE_HOLD_MIN_MS + 10);
    });
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(eyesRoot().dataset.gazeMs).toBe(String(GAZE_RETURN_MS));
  });

  it('a wander interrupted by minimizing STILL comes home (no gaze drift, ever)', () => {
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0) // pick → saccade
      .mockReturnValueOnce(0.9) // pre-gaze blink roll → no
      .mockReturnValueOnce(0) // target x → -0.35
      .mockReturnValueOnce(0) // target y
      .mockReturnValueOnce(0) // hold → SACCADE_HOLD_MIN_MS
      .mockReturnValue(0.9);
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.gazeX).toBe('-0.35');
    // Minimize MID-HOLD: the wander loop is torn down…
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    act(() => {
      vi.advanceTimersByTime(SACCADE_HOLD_MIN_MS + 100);
    });
    // …but the homing timer survives: restored eyes sit exactly at center.
    fireEvent.click(screen.getByRole('button', { name: 'eyes.restore' }));
    expect(eyesRoot().dataset.gazeX).toBe('0');
  });

  it('plays a one-shot gesture class then clears it (rng → squint on calm)', () => {
    // Calm cumulative weights: 0.6 lands on 'squint'.
    vi.spyOn(Math, 'random').mockReturnValue(0.6);
    renderWidget();
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    act(() => {
      vi.advanceTimersByTime(
        IDLE_GESTURE_MIN_DELAY_MS +
          0.6 * (IDLE_GESTURE_MAX_DELAY_MS - IDLE_GESTURE_MIN_DELAY_MS) +
          10
      );
    });
    expect(eyesRoot().dataset.gesture).toBe('squint');
    act(() => {
      vi.advanceTimersByTime(GESTURE_DURATION_MS.squint + 10);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('while LIA speaks aloud the gaze holds on the person: no reading walk, no idle gesture', () => {
    // Owner rule 2026-11-14: LIA speaks TO the person. Eyes walking a line
    // from left to right read a text; they do not address anybody.
    useEyesSignalsStore.getState().setAudioPlaying(true);
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    renderWidget({ chatStatus: 'idle' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('speaking');
    for (let beat = 0; beat < 12; beat += 1) {
      act(() => {
        vi.advanceTimersByTime(350);
      });
      expect(eyesRoot().dataset.gazeX, `${beat} beats into the speech`).toBe('0');
      expect(eyesRoot().dataset.gazeY).toBe('0');
      expect(eyesRoot().dataset.gesture).toBeUndefined();
    }
  });

  it('no glance leaves the person while LIA speaks', () => {
    // The draws that open the idle life with a saccade (the wander test's own).
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0) // pick → saccade
      .mockReturnValueOnce(0.9) // pre-gaze blink roll → no
      .mockReturnValueOnce(0) // target x → -0.35
      .mockReturnValueOnce(0) // target y → -0.22
      .mockReturnValue(0.9);
    useEyesSignalsStore.getState().setAudioPlaying(true);
    renderWidget({ chatStatus: 'idle' });
    settleMask();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('speaking');
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('a glance under way when the voice starts comes back to the person', () => {
    // Mount order: blink delay, idle delay; tick order: pick, pre-gaze blink
    // roll, target x, target y, hold (a glance holds far longer than this test).
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0) // pick → saccade
      .mockReturnValueOnce(0.9) // pre-gaze blink roll → no
      .mockReturnValueOnce(0) // target x → -0.35
      .mockReturnValueOnce(0) // target y → -0.22
      .mockReturnValue(0.9); // hold → long
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.gazeX).toBe('-0.35');

    act(() => {
      useEyesSignalsStore.getState().setAudioPlaying(true);
    });
    settleMask();

    expect(eyesRoot().dataset.expression).toBe('speaking');
    expect(eyesRoot().dataset.gazeX).toBe('0');
  });

  it('changes attention without forcing a masking blink', () => {
    const { rerender } = renderWidget({ chatStatus: 'idle' });
    rerender(<EyesWidget chatStatus="sending" streamPhase="answer" hitlAwaiting={false} />);
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().dataset.blinkMask).toBeUndefined();
    expect(eyesRoot().dataset.blinking).toBeUndefined();
  });

  it('leaves the declared mood stable while the rig owns idle scenes', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.95);
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MAX_DELAY_MS + 100);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
    expect(eyesRoot().dataset.blinkMask).toBeUndefined();
  });

  it('the idle life never plays over a directed expression (streaming)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.7);
    renderWidget({ chatStatus: 'streaming', streamPhase: 'progress' });
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MAX_DELAY_MS + 100);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });
});

describe('EyesWidget — touch toolbar (tap to summon)', () => {
  function toolbarOf(): HTMLElement {
    const btn = screen.getByRole('button', { name: 'eyes.cycle_size' });
    return btn.parentElement as HTMLElement;
  }

  /** Force every media query verdict (true only for the listed queries). */
  function mockMedia(matching: readonly string[]) {
    vi.spyOn(window, 'matchMedia').mockImplementation(
      query =>
        ({
          matches: matching.includes(query),
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as MediaQueryList
    );
  }

  it('hidden by default AND inert (never invisible-yet-clickable)', () => {
    renderWidget();
    expect(toolbarOf().className).toContain('pointer-events-none');
    expect(toolbarOf().className).toContain('opacity-0');
  });

  it('on touch screens, a tap toggles the toolbar and it auto-hides', () => {
    mockMedia(['(hover: none)']);
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    fireEvent.click(group);
    expect(toolbarOf().className).toContain('opacity-100');
    expect(toolbarOf().className).toContain('pointer-events-auto');
    // Second tap dismisses.
    fireEvent.click(group);
    expect(toolbarOf().className).toContain('opacity-0');
    // Summon again → the timer hides it on its own.
    fireEvent.click(group);
    act(() => {
      vi.advanceTimersByTime(4100);
    });
    expect(toolbarOf().className).toContain('opacity-0');
  });

  it('on hover-capable screens a click never summons the toolbar', () => {
    // Explicit desktop verdicts — never rely on mock-restore ordering.
    mockMedia(['(hover: hover) and (pointer: fine)']);
    renderWidget();
    fireEvent.click(screen.getByRole('group', { name: 'eyes.widget_label' }));
    expect(toolbarOf().className).toContain('opacity-0');
  });
});

describe('EyesWidget — text being written has the face', () => {
  /** Declare on the page where the answer is being written. */
  function writeAnswerAt(rect: DOMRect): HTMLElement {
    const block = document.createElement('div');
    for (const [name, value] of Object.entries(gazeTargetProps('answer')))
      block.setAttribute(name, value);
    block.getBoundingClientRect = () => rect;
    document.body.append(block);
    return block;
  }

  function parkFaceAt(rect: DOMRect): void {
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    vi.spyOn(group, 'getBoundingClientRect').mockReturnValue(rect);
  }

  function nextLook(): void {
    act(() => {
      vi.advanceTimersByTime(GAZE_TARGET_REFRESH_MS + 20);
    });
  }

  afterEach(() => {
    document.querySelectorAll('[data-eyes-target]').forEach(block => block.remove());
  });

  it('looks at the answer where the screen says it is written, wherever the face is parked', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    // The end of the block is at (512, 700) in a 1024 x 768 window.
    writeAnswerAt(new DOMRect(212, 500, 600, 200));
    renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    // Docked above the thread: the text is straight below.
    parkFaceAt(new DOMRect(462, 0, 100, 100));
    nextLook();
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(eyesRoot().dataset.gazeY).toBe('1');
    // Parked beside the text: the same text is to its left, at its own height.
    parkFaceAt(new DOMRect(900, 650, 100, 100));
    nextLook();
    expect(Number(eyesRoot().dataset.gazeX)).toBeCloseTo((512 - 950) / 512, 3);
    expect(eyesRoot().dataset.gazeY).toBe('0');
  });

  it('lets go of the text when the answer is delivered', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    writeAnswerAt(new DOMRect(212, 500, 600, 200));
    const { rerender } = renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    parkFaceAt(new DOMRect(462, 0, 100, 100));
    nextLook();
    expect(eyesRoot().dataset.gazeY).toBe('1');
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + 20);
    });
    expect(eyesRoot().dataset.gazeY).toBe('0');
  });

  it('lets go of the text when the delivered answer leaves the same attentive face', () => {
    // A curious mood rests on the attentive face: delivering the answer
    // changes nothing but what the face looks at.
    usePsycheStore.setState({ enabled: true, moodLabel: 'curious' });
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    writeAnswerAt(new DOMRect(212, 500, 600, 200));
    const { rerender } = renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    parkFaceAt(new DOMRect(462, 0, 100, 100));
    nextLook();
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().dataset.gazeY).toBe('1');
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    act(() => {
      vi.advanceTimersByTime(20);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().dataset.gazeY).toBe('0');
  });

  it('plays no gesture of its own and wanders nowhere while the answer is written', () => {
    // 0.6 lands on the squint gesture of a calm face at rest (see above).
    vi.spyOn(Math, 'random').mockReturnValue(0.6);
    useEyesSignalsStore.getState().beginTurn('answer');
    renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    // No declared place on this page: the look stays centred, and still.
    for (let elapsed = 0; elapsed < 4 * IDLE_GESTURE_MAX_DELAY_MS; elapsed += 250) {
      act(() => {
        vi.advanceTimersByTime(250);
      });
      expect(eyesRoot().dataset.gesture).toBeUndefined();
      expect(eyesRoot().dataset.gazeX).toBe('0');
      expect(eyesRoot().dataset.gazeY).toBe('0');
    }
  });

  it('keeps the look on the text when the cursor moves', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    const media = window.matchMedia('');
    vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
      ...media,
      media: query,
      matches: query === '(hover: hover) and (pointer: fine)',
    }));
    // No declared place yet (the first words are not on screen): the look
    // waits at the centre, it does not go to the cursor meanwhile.
    renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    parkFaceAt(new DOMRect(462, 300, 100, 100));
    const moveCursor = () =>
      act(() => {
        window.dispatchEvent(new MouseEvent('pointermove', { clientX: 10, clientY: 10 }));
        vi.advanceTimersByTime(50);
      });
    moveCursor();
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(eyesRoot().dataset.gazeY).toBe('0');
    // The words arrive: the look goes to them, and stays there.
    writeAnswerAt(new DOMRect(212, 500, 600, 200));
    nextLook();
    moveCursor();
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(Number(eyesRoot().dataset.gazeY)).toBeCloseTo((700 - 350) / 384, 3);
  });
});

describe('EyesWidget — what is typed and what arrives have the face', () => {
  function declare(target: string, rect: DOMRect): HTMLElement {
    const element = document.createElement('div');
    for (const [name, value] of Object.entries(gazeTargetProps(target as 'input')))
      element.setAttribute(name, value);
    element.getBoundingClientRect = () => rect;
    document.body.append(element);
    return element;
  }

  function frontToast(rect: DOMRect): HTMLElement {
    const element = document.createElement('li');
    element.setAttribute('data-sonner-toast', '');
    element.setAttribute('data-front', 'true');
    element.getBoundingClientRect = () => rect;
    document.body.append(element);
    return element;
  }

  function parkFaceAt(rect: DOMRect): void {
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    vi.spyOn(group, 'getBoundingClientRect').mockReturnValue(rect);
  }

  function nextLook(): void {
    act(() => {
      vi.advanceTimersByTime(GAZE_TARGET_REFRESH_MS + 20);
    });
  }

  afterEach(() => {
    document.querySelectorAll('[data-eyes-target], [data-sonner-toast]').forEach(e => e.remove());
  });

  beforeEach(() => {
    // A quiet idle draw: what these scenarios see is the look, not a gesture.
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
  });

  it('looks at the field being typed in where it is, not below the face', () => {
    // Parked beside the thread, low on the right: the field is to its left.
    declare('input', new DOMRect(212, 650, 600, 80));
    renderWidget({ chatStatus: 'idle' });
    parkFaceAt(new DOMRect(900, 600, 100, 100));
    act(() => {
      useEyesSignalsStore.getState().recordTyping();
      vi.advanceTimersByTime(1);
    });
    nextLook();
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(Number(eyesRoot().dataset.gazeX)).toBeCloseTo((512 - 950) / 512, 3);
    expect(Number(eyesRoot().dataset.gazeY)).toBeCloseTo((690 - 650) / 384, 3);
  });

  it('looks down at the field when the screen declares none', () => {
    renderWidget({ chatStatus: 'idle' });
    parkFaceAt(new DOMRect(900, 600, 100, 100));
    act(() => {
      useEyesSignalsStore.getState().recordTyping();
      vi.advanceTimersByTime(1);
    });
    nextLook();
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(eyesRoot().dataset.gazeY).toBe('1');
  });

  it('looks at the toast that has just appeared, at the top of the page', () => {
    frontToast(new DOMRect(362, 32, 300, 60));
    renderWidget({ chatStatus: 'idle' });
    parkFaceAt(new DOMRect(900, 600, 100, 100));
    act(() => {
      useEyesSignalsStore.getState().recordNotification();
      vi.advanceTimersByTime(1);
    });
    settleMask();
    nextLook();
    expect(eyesRoot().dataset.expression).toBe('surprise');
    expect(Number(eyesRoot().dataset.gazeX)).toBeCloseTo((512 - 950) / 512, 3);
    expect(eyesRoot().dataset.gazeY).toBe('-1');
  });

  it('looks at the place a page with no toast shows its notifications', () => {
    declare('notification', new DOMRect(920, 700, 44, 44));
    renderWidget({ chatStatus: 'idle' });
    parkFaceAt(new DOMRect(462, 300, 100, 100));
    act(() => {
      useEyesSignalsStore.getState().recordNotification();
      vi.advanceTimersByTime(1);
    });
    settleMask();
    nextLook();
    expect(Number(eyesRoot().dataset.gazeX)).toBeCloseTo((942 - 512) / 512, 3);
    expect(Number(eyesRoot().dataset.gazeY)).toBeCloseTo((722 - 350) / 384, 3);
  });

  it('looks up, where the toaster is, when nothing on the page shows the notification', () => {
    renderWidget({ chatStatus: 'idle' });
    parkFaceAt(new DOMRect(462, 300, 100, 100));
    act(() => {
      useEyesSignalsStore.getState().recordNotification();
      vi.advanceTimersByTime(1);
    });
    settleMask();
    nextLook();
    expect(eyesRoot().dataset.gazeX).toBe('0');
    expect(eyesRoot().dataset.gazeY).toBe('-1');
  });
});

describe('EyesWidget — the wait', () => {
  const ANSWER = 'answer-1';

  /** One execution event of the turn in flight, as the stream delivers it. */
  function tool(
    invocation: string,
    phase: Activity['phase'],
    outcome: Activity['outcome'] = null
  ): Activity {
    return {
      version: 1,
      run_id: 'run-1',
      invocation_id: invocation,
      family: 'reading',
      intent: 'read',
      phase,
      outcome,
    };
  }

  function deliver(event: Activity): void {
    act(() => {
      useEyesSignalsStore.getState().recordActivity(event, ANSWER, false);
      vi.advanceTimersByTime(1);
    });
  }

  function elapse(ms: number): void {
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  }

  /** The face of a turn that is working: sent, begun, no answer yet. */
  function renderWorking(): ReturnType<typeof render> {
    const result = renderWidget({ chatStatus: 'streaming', streamPhase: 'progress' });
    act(() => {
      useEyesSignalsStore.getState().beginTurn(ANSWER);
      vi.advanceTimersByTime(1);
    });
    return result;
  }

  beforeEach(() => {
    // A quiet idle draw (a flicker), and no spontaneous blink for 4.5 s: what
    // these scenarios see is the exchange, not the face's own life.
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
  });

  it('acknowledges a message the moment it is sent, and once', () => {
    const { rerender } = renderWidget({ chatStatus: 'idle' });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    rerender(<EyesWidget chatStatus="sending" streamPhase="answer" hitlAwaiting={false} />);
    elapse(1);
    expect(eyesRoot().dataset.gesture).toBe('perk');
    elapse(GESTURE_DURATION_MS.perk + 10);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    // Still the same turn: there is nothing more to acknowledge.
    rerender(<EyesWidget chatStatus="streaming" streamPhase="progress" hitlAwaiting={false} />);
    elapse(1500);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    // The next message is another one.
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    elapse(1500);
    rerender(<EyesWidget chatStatus="sending" streamPhase="answer" hitlAwaiting={false} />);
    elapse(1);
    expect(eyesRoot().dataset.gesture).toBe('perk');
  });

  it('lets the acknowledgement land before the thought arrives', () => {
    // The person was typing: the face is already attentive, and has been for
    // longer than any hold. Without the beat's own hold the thought would
    // replace it in the frame that follows the send, and cut the beat.
    useEyesSignalsStore.getState().recordTyping();
    const { rerender } = renderWidget({ chatStatus: 'idle' });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    elapse(MIN_EXPRESSION_HOLD_MS + 300);
    rerender(<EyesWidget chatStatus="sending" streamPhase="answer" hitlAwaiting={false} />);
    elapse(1);
    expect(eyesRoot().dataset.gesture).toBe('perk');
    elapse(80);
    rerender(<EyesWidget chatStatus="streaming" streamPhase="progress" hitlAwaiting={false} />);
    elapse(1);
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().dataset.gesture).toBe('perk');
    elapse(MIN_EXPRESSION_HOLD_MS);
    expect(eyesRoot().dataset.expression).toBe('thinking');
  });

  it('acknowledges nothing when it is mounted on a turn already under way', () => {
    renderWidget({ chatStatus: 'sending' });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    elapse(300);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('marks a tool that finished with a blink and a lift of the brows', () => {
    renderWorking();
    deliver(tool('first', 'started'));
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    expect(eyesRoot().dataset.blinking).toBeUndefined();
    deliver(tool('first', 'finished', 'succeeded'));
    expect(eyesRoot().dataset.gesture).toBe('brow-twitch');
    expect(eyesRoot().dataset.blinking).toBe('true');
    elapse(GESTURE_DURATION_MS['brow-twitch'] + 10);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('marks a draft that was prepared like a result that was found', () => {
    renderWorking();
    deliver(tool('draft', 'started'));
    deliver(tool('draft', 'finished', 'prepared'));
    expect(eyesRoot().dataset.gesture).toBe('brow-twitch');
  });

  it.each(['failed', 'cancelled', 'waiting', 'unknown'] as const)(
    'marks nothing for a tool that ended %s',
    outcome => {
      renderWorking();
      deliver(tool('first', 'started'));
      deliver(tool('first', 'finished', outcome));
      expect(eyesRoot().dataset.gesture).toBeUndefined();
      expect(eyesRoot().dataset.blinking).toBeUndefined();
      elapse(600);
      expect(eyesRoot().dataset.gesture).toBeUndefined();
    }
  );

  it('marks each tool, and each one once', () => {
    renderWorking();
    deliver(tool('first', 'started'));
    deliver(tool('first', 'finished', 'succeeded'));
    expect(eyesRoot().dataset.gesture).toBe('brow-twitch');
    elapse(GESTURE_DURATION_MS['brow-twitch'] + 10);
    // The stream delivers the same event again: duplicates are absorbed.
    deliver(tool('first', 'finished', 'succeeded'));
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    deliver(tool('second', 'started'));
    deliver(tool('second', 'finished', 'succeeded'));
    expect(eyesRoot().dataset.gesture).toBe('brow-twitch');
    elapse(GESTURE_DURATION_MS['brow-twitch'] + 10);
    // The delivered answer recalls the same evidence (its time is stamped
    // again): a recall is not another tool.
    act(() => {
      useEyesSignalsStore.getState().completeTurn(ANSWER);
      vi.advanceTimersByTime(1);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('marks nothing it did not see: a face mounted after the tool finished', () => {
    act(() => {
      useEyesSignalsStore.getState().beginTurn(ANSWER);
      useEyesSignalsStore.getState().recordActivity(tool('first', 'started'), ANSWER, false);
      useEyesSignalsStore
        .getState()
        .recordActivity(tool('first', 'finished', 'succeeded'), ANSWER, false);
    });
    renderWidget({ chatStatus: 'streaming', streamPhase: 'progress' });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    elapse(600);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('plays neither beat under reduced motion', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation(reducedMotionQuery);
    const { rerender } = renderWidget({ chatStatus: 'idle' });
    rerender(<EyesWidget chatStatus="sending" streamPhase="answer" hitlAwaiting={false} />);
    elapse(1);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    rerender(<EyesWidget chatStatus="streaming" streamPhase="progress" hitlAwaiting={false} />);
    act(() => {
      useEyesSignalsStore.getState().beginTurn(ANSWER);
      vi.advanceTimersByTime(1);
    });
    deliver(tool('first', 'started'));
    deliver(tool('first', 'finished', 'succeeded'));
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    expect(eyesRoot().dataset.blinking).toBeUndefined();
  });
});

describe('EyesWidget — emotes and quiet presence', () => {
  it('a HITL question floats a "?" above the eyes, and it leaves on resolution', () => {
    const { rerender } = renderWidget({ hitlAwaiting: true });
    settleMask();
    expect(document.querySelector('.lia-emote')?.textContent).toBe('?');
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    // The return to idle is not urgent: minimum hold first, then the masked
    // swap — the "?" starts leaving when the idle face lands.
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS - MASK_APPLY_DELAY_MS);
    });
    expect(document.querySelector('.lia-emote')?.classList.contains('is-leaving')).toBe(true);
    act(() => {
      vi.advanceTimersByTime(EMOTE_EXIT_MS + 10);
    });
    expect(document.querySelector('.lia-emote')).toBeNull();
  });

  it('deep sleep floats the drifting "z"', () => {
    // Pinned for the same reason as the wake-startle test: a free-RNG flicker
    // during the long doze can hold the frame at the assertion instant.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    fallAsleep();
    expect(document.querySelector('.lia-emote')?.getAttribute('data-emote')).toBe('z');
  });

  it('a formerly silly RNG draw remains a gaze request, with no slapstick gesture', () => {
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9)
      .mockReturnValueOnce(0)
      .mockReturnValueOnce(0.01)
      .mockReturnValue(0.9);
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    expect(eyesRoot().dataset.gazeX).not.toBe('0');
  });
});

describe('EyesWidget — character moments', () => {
  it('being carried startles: wide eyes while dragging, back to normal on drop', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    fireEvent.pointerDown(group, { pointerId: 7, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(group, { pointerId: 7, clientX: 170, clientY: 150 });
    expect(eyesRoot().dataset.expression).toBe('surprise');
    fireEvent.pointerUp(group, { pointerId: 7, clientX: 170, clientY: 150 });
    expect(eyesRoot().dataset.expression).not.toBe('surprise');
  });

  it('waking from DEEP sleep plays the full startle: jolt, look around, settle', () => {
    // 0.5 keeps the idle life benign across the long doze + settle window:
    // every gesture pick
    // lands on saccade/glance/perk, none of which touch data-expression —
    // free RNG here let a flicker steal the frame right at the settle
    // assertion (seen only on CI runners).
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    fallAsleep();
    // Age the sleep that actually landed, then let the real heartbeat run:
    // inactivity alone cannot earn the deep-sleep startle.
    observeInactivityAt(Date.now() + SHORT_NAP_MS);
    expect(eyesRoot().dataset.expression).toBe('sleep');
    fireEvent.keyDown(document.body, { key: 'a' });
    act(() => {
      vi.advanceTimersByTime(10);
    });
    expect(eyesRoot().dataset.expression).toBe('surprise');
    act(() => {
      vi.advanceTimersByTime(WAKE_PERFORMANCE[0].ms + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    const total = WAKE_PERFORMANCE.reduce((sum, s) => sum + s.ms, 0);
    act(() => {
      vi.advanceTimersByTime(total + 1200);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
  });

  it('waking from a SHORT nap is a quick recollection, not a startle', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    fallAsleep();
    expect(eyesRoot().dataset.expression).toBe('sleep');
    // Woken moments after dozing off: attentive beat, then back to the room —
    // never the full jolt.
    fireEvent.keyDown(document.body, { key: 'a' });
    act(() => {
      vi.advanceTimersByTime(10);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    const total = WAKE_SHORT_PERFORMANCE.reduce((sum, s) => sum + s.ms, 0);
    act(() => {
      vi.advanceTimersByTime(total + 1200);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
  });
});

describe('EyesWidget — motion one-shots', () => {
  it('a double-click right after a drag drop does NOT wink (glitch guard)', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    fireEvent.pointerDown(group, { pointerId: 3, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(group, { pointerId: 3, clientX: 180, clientY: 160 });
    fireEvent.pointerUp(group, { pointerId: 3, clientX: 180, clientY: 160 });
    fireEvent.doubleClick(group);
    expect(eyesRoot().dataset.expression).not.toBe('wink');
    // After the suppression window, the wink works again.
    act(() => {
      vi.advanceTimersByTime(500);
    });
    fireEvent.doubleClick(group);
    expect(eyesRoot().dataset.expression).toBe('wink');
  });

  it('double-click winks, then reverts', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    fireEvent.doubleClick(group);
    expect(eyesRoot().dataset.expression).toBe('wink');
    act(() => {
      vi.advanceTimersByTime(WINK_DURATION_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
  });

  it('blinks on schedule and clears the flag after one cycle (double blink at low RNG)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    renderWidget();
    expect(eyesRoot().dataset.blinking === 'true').toBe(false);
    // rng=0 → first blink exactly at BLINK_MIN_DELAY_MS.
    act(() => {
      vi.advanceTimersByTime(BLINK_MIN_DELAY_MS);
    });
    expect(eyesRoot().dataset.blinking === 'true').toBe(true);
    act(() => {
      vi.advanceTimersByTime(BLINK_DURATION_MS);
    });
    expect(eyesRoot().dataset.blinking === 'true').toBe(false);
    // rng=0 → double blink: second cycle after the gap.
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(eyesRoot().dataset.blinking === 'true').toBe(true);
  });
});

describe('EyesWidget — liveliness beats (2026-08-21 batch)', () => {
  it('reflects the mood family on data-family (breathing/CSS channel)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    expect(eyesRoot().dataset.family).toBe('calm');
    act(() => {
      usePsycheStore.setState({ enabled: true, moodLabel: 'playful' });
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.family).toBe('lively');
  });

  it('a mood shift updates temperament without inserting a fake joyful response', () => {
    renderWidget();
    act(() => {
      usePsycheStore.setState({ enabled: true, moodLabel: 'playful' });
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + 10);
    });
    expect(eyesRoot().dataset.family).toBe('lively');
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().dataset.gazeY).toBe('0');
  });

  it('returns to rest after typing expires without inventing a question', () => {
    renderWidget();
    act(() => {
      useEyesSignalsStore.getState().recordTyping();
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
    expect(document.querySelector('.lia-emote')).toBeNull();
  });

  it('returning to the tab after a real absence earns a welcome perk', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    const hidden = vi.spyOn(document, 'hidden', 'get');
    hidden.mockReturnValue(true);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
      vi.advanceTimersByTime(RETURN_PERK_MIN_AWAY_MS + 1000);
    });
    hidden.mockReturnValue(false);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(eyesRoot().dataset.gesture).toBe('perk');
    act(() => {
      vi.advanceTimersByTime(GESTURE_DURATION_MS.perk + 10);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('a short tab switch earns no perk', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    const hidden = vi.spyOn(document, 'hidden', 'get');
    hidden.mockReturnValue(true);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
      vi.advanceTimersByTime(2000);
    });
    hidden.mockReturnValue(false);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('overlapping blink pulses never cut the lid mid-cycle (last pulse wins)', () => {
    // Force the pre-gaze blink (rng 0 < probability) on an immediate wander.
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay -> MIN
      .mockReturnValueOnce(0) // pick -> saccade
      .mockReturnValueOnce(0) // pre-gaze blink roll -> YES
      .mockReturnValue(0.9);
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    // The pre-gaze blink pulse is on.
    expect(eyesRoot().dataset.blinking === 'true').toBe(true);
    // A masked transition lands 200 ms later and re-pulses the SAME timer:
    // the lid must stay down past the first pulse's own 420 ms deadline.
    act(() => {
      vi.advanceTimersByTime(200);
    });
    act(() => {
      useEyesSignalsStore.getState().setReaction('joy', Date.now());
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS - 200);
    });
    expect(eyesRoot().dataset.blinking === 'true').toBe(true);
    // ...and clears one full cycle after the LAST pulse, not the first.
    act(() => {
      vi.advanceTimersByTime(BLINK_DURATION_MS + 50);
    });
    expect(eyesRoot().dataset.blinking === 'true').toBe(false);
  });

  it('a notification cuts a running idle beat short (the glance must not be hidden)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    act(() => {
      useEyesSignalsStore.getState().recordTyping();
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
    });
    // Let the wonder beat start (typing expired, heartbeat noticed)...
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
    // ...then a notification lands mid-beat: the surprised glance wins.
    act(() => {
      useEyesSignalsStore.getState().recordNotification();
    });
    act(() => {
      vi.advanceTimersByTime(10);
    });
    expect(eyesRoot().dataset.expression).toBe('surprise');
  });

  it('anti-zapping: a non-urgent burst keeps the first face its minimum beat', () => {
    renderWidget();
    act(() => {
      useEyesSignalsStore.getState().setReaction('joy');
    });
    act(() => {
      vi.advanceTimersByTime(10);
    });
    expect(eyesRoot().dataset.expression).toBe('joy');
    // A second, non-urgent frame right behind: it must WAIT the hold out.
    act(() => {
      useEyesSignalsStore.getState().setReaction('sad');
    });
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(eyesRoot().dataset.expression).toBe('joy');
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('sad');
  });
});

describe('EyesWidget — cartoon accessories (RNG-pinned)', () => {
  it('brings a bead of sweat to a worried face, then takes it back', () => {
    // Rolls low: the accessory fires. Pinning the RNG is what makes a
    // deliberately RARE beat testable at all.
    vi.spyOn(Math, 'random').mockReturnValue(0.02);
    renderWidget({ chatStatus: 'error' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('worried');
    expect(document.querySelector('.lia-accessory')?.getAttribute('data-accessory')).toBe('sweat');

    act(() => {
      vi.advanceTimersByTime(ACCESSORY_DURATION_MS.sweat + 50);
    });
    expect(document.querySelector('.lia-accessory')).toBeNull();
  });

  it('takes back a sparkle EARNED BY AN ACCENT, exactly like any other', () => {
    // An accessory set by one owner and cleared by another is an accessory
    // that never clears: the accent path set the sparkle and scheduled
    // nothing, so it sat on the face until the next expression change.
    useEyesSignalsStore.getState().setReaction('excited', 1.4, 'sparkle');
    renderWidget({ chatStatus: 'idle' });
    settleMask();
    expect(document.querySelector('.lia-accessory')?.getAttribute('data-accessory')).toBe(
      'sparkle'
    );

    act(() => {
      vi.advanceTimersByTime(ACCESSORY_DURATION_MS.sparkle + 50);
    });
    expect(document.querySelector('.lia-accessory')).toBeNull();
  });

  it('never plays an accent beat under reduced motion', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation(reducedMotionQuery);
    useEyesSignalsStore.getState().setReaction('excited', 1.4, 'sparkle');
    renderWidget({ chatStatus: 'idle' });
    settleMask();
    expect(document.querySelector('.lia-accessory')).toBeNull();
  });

  it('cancels an in-flight wink when reduced motion changes without replaying it on return', () => {
    let reduced = false;
    const events = new EventTarget();
    const media: MediaQueryList = {
      get matches() {
        return reduced;
      },
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: events.addEventListener.bind(events),
      removeEventListener: events.removeEventListener.bind(events),
      dispatchEvent: events.dispatchEvent.bind(events),
    };
    vi.spyOn(window, 'matchMedia').mockReturnValue(media);
    const { unmount } = renderWidget();
    fireEvent.doubleClick(screen.getByRole('group'));
    expect(eyesRoot().dataset.expression).toBe('wink');
    act(() => {
      reduced = true;
      media.dispatchEvent(new Event('change'));
    });
    expect(eyesRoot().dataset.expression).not.toBe('wink');
    act(() => {
      reduced = false;
      media.dispatchEvent(new Event('change'));
    });
    expect(eyesRoot().dataset.expression).not.toBe('wink');
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('brings nothing on an unlucky roll — most arrivals stay plain', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    renderWidget({ chatStatus: 'error' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('worried');
    expect(document.querySelector('.lia-accessory')).toBeNull();
  });

  it('never plays one under reduced motion — a flourish is the first thing spared', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.02);
    vi.spyOn(window, 'matchMedia').mockImplementation(reducedMotionQuery);
    renderWidget({ chatStatus: 'error' });
    settleMask();
    expect(document.querySelector('.lia-accessory')).toBeNull();
  });
});

describe('EyesWidget — the restore dot moves too (2026-09-10)', () => {
  beforeEach(() => {
    localStorage.clear();
    useEyesWidgetStore.getState().reset();
  });

  it('can be dragged, and the drop does not restore the eyes', () => {
    renderWidget();
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    const dot = screen.getByRole('button', { name: 'eyes.restore' });

    fireEvent.pointerDown(dot, { pointerId: 5, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(dot, { pointerId: 5, clientX: 170, clientY: 150 });
    fireEvent.pointerUp(dot, { pointerId: 5, clientX: 170, clientY: 150 });
    fireEvent.click(dot);

    expect(useEyesWidgetStore.getState().position).not.toBeNull();
    expect(document.querySelector('.lia-eyes')).toBeNull();
  });

  it('sits where the eyes were dragged, and a plain click restores them there', () => {
    useEyesWidgetStore.getState().setPosition({ xPct: 30, yPct: 40 });
    renderWidget();
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    const dot = screen.getByRole('button', { name: 'eyes.restore' });

    expect(parseFloat(dot.style.left)).toBeCloseTo(window.innerWidth * 0.3);
    expect(dot.className).not.toContain('bottom-32');
    fireEvent.click(dot);

    expect(document.querySelector('.lia-eyes')).not.toBeNull();
  });
});

describe('EyesWidget — an answer delivered', () => {
  function elapse(ms: number): void {
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  }

  /** The answer of a turn that just completed, as the chat wiring stores it. */
  function deliver(expression: 'neutral' | 'thinking', accent: 'none' | 'nod' = 'none'): void {
    act(() => {
      useEyesSignalsStore.getState().setReaction(expression, 1, accent);
      vi.advanceTimersByTime(1);
    });
  }

  beforeEach(() => {
    // A quiet idle draw and no spontaneous blink in the window: what these
    // scenarios see is the delivery, not the face's own life.
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
  });

  it('presents a delivered answer, then hands it over three seconds later', () => {
    renderWidget({ chatStatus: 'idle' });
    deliver('neutral');
    expect(eyesRoot().dataset.gesture).toBe('present-factual');
    elapse(HAND_OVER_AFTER_MS - 20);
    expect(eyesRoot().dataset.gesture).toBe('present-factual');
    elapse(40);
    expect(eyesRoot().dataset.gesture).toBe('listen');
    elapse(GESTURE_DURATION_MS.listen + 10);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('presents the answer once its own face has landed, never under the face it replaces', () => {
    // The store learns of the answer while the page still says « streaming »:
    // a beat started then was wiped a commit later by the arrival of the
    // answer's face (the rig interrupts every beat on a new expression).
    const { rerender } = renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    settleMask();
    expect(eyesRoot().dataset.expression).not.toBe('neutral');
    deliver('neutral');
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    elapse(MIN_EXPRESSION_HOLD_MS + 20);
    expect(eyesRoot().dataset.expression).toBe('neutral');
    expect(eyesRoot().dataset.gesture).toBe('present-factual');
  });

  it('a voice that starts speaking takes the face from the presentation', () => {
    // Owner report 2026-11-14: with a spoken comment or a Live voice, the answer's
    // presentation played on over the first words and the lips followed nothing.
    renderWidget({ chatStatus: 'idle' });
    deliver('neutral');
    expect(eyesRoot().dataset.gesture).toBe('present-factual');
    elapse(800);
    act(() => {
      useEyesSignalsStore.getState().setAudioPlaying(true);
    });
    elapse(20);
    expect(eyesRoot().dataset.expression).toBe('speaking');
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('hands nothing over while the voice is still speaking', () => {
    renderWidget({ chatStatus: 'idle' });
    deliver('neutral');
    elapse(800);
    act(() => {
      useEyesSignalsStore.getState().setAudioPlaying(true);
    });
    // « À toi » would fall due here, in the middle of a sentence.
    elapse(HAND_OVER_AFTER_MS);
    expect(eyesRoot().dataset.expression).toBe('speaking');
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    elapse(GESTURE_DURATION_MS.listen);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('presents nothing over a voice already speaking when the answer lands', () => {
    useEyesSignalsStore.getState().setAudioPlaying(true);
    renderWidget({ chatStatus: 'idle' });
    settleMask();
    deliver('neutral');
    expect(eyesRoot().dataset.expression).toBe('speaking');
    for (let beat = 0; beat < 8; beat += 1) {
      elapse(500);
      expect(eyesRoot().dataset.gesture, `${beat} beats into the speech`).toBeUndefined();
    }
  });

  it('presents nothing once the voice that spoke the answer stops or pauses', () => {
    // Between two phrases the voice is silent for a moment: a presentation starting
    // there would be cut by the next phrase, a twitch under the answer being spoken.
    useEyesSignalsStore.getState().setAudioPlaying(true);
    renderWidget({ chatStatus: 'idle' });
    settleMask();
    deliver('neutral');
    elapse(1200);
    act(() => {
      useEyesSignalsStore.getState().setAudioPlaying(false);
    });
    elapse(MIN_EXPRESSION_HOLD_MS + 20);
    expect(eyesRoot().dataset.expression).toBe('neutral');
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    elapse(HAND_OVER_AFTER_MS);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('hands nothing over to someone who started writing meanwhile', () => {
    renderWidget({ chatStatus: 'idle' });
    deliver('neutral');
    elapse(1500);
    act(() => {
      useEyesSignalsStore.getState().recordTyping();
    });
    elapse(HAND_OVER_AFTER_MS);
    expect(eyesRoot().dataset.gesture).not.toBe('listen');
  });

  it('plays the accent the model declared instead, and hands nothing over after it', () => {
    renderWidget({ chatStatus: 'idle' });
    deliver('neutral', 'nod');
    expect(eyesRoot().dataset.gesture).toBe('nod');
    elapse(HAND_OVER_AFTER_MS + 100);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('leaves no hand-over pending once it is gone, even one a newer answer replaced', () => {
    const { unmount } = renderWidget({ chatStatus: 'idle' });
    deliver('neutral');
    elapse(500);
    deliver('neutral');
    elapse(500);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('wears the thought bubble while it works, and not over a careful answer it delivered', () => {
    const working = renderWidget({ chatStatus: 'streaming', streamPhase: 'progress' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('thinking');
    expect(document.querySelector('.lia-emote')?.getAttribute('data-emote')).toBe('…');
    working.unmount();
    useEyesSignalsStore.getState().reset();

    renderWidget({ chatStatus: 'idle' });
    deliver('thinking');
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('thinking');
    expect(document.querySelector('.lia-emote')).toBeNull();
  });

  it('gives the face back to its own life once the hand-over has played, not before', () => {
    // Every draw at 0: the idle life ticks every 1.9 s and opens with a saccade.
    vi.spyOn(Math, 'random').mockReturnValue(0);
    renderWidget({ chatStatus: 'idle' });
    deliver('neutral');
    // 5.7 s: the answer no longer holds the face, but « à toi » is still playing.
    elapse(3 * IDLE_GESTURE_MIN_DELAY_MS + 400 - 1);
    expect(eyesRoot().dataset.gazeX).toBe('0');
    // 7.6 s: the hand-over is over, and the next tick of its life is its own.
    elapse(IDLE_GESTURE_MIN_DELAY_MS);
    expect(eyesRoot().dataset.gazeX).not.toBe('0');
  });
});

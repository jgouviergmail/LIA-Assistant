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

import { EyesWidget } from '../EyesWidget';
import { anchoredPosition } from '../useEyesAnchor';
import {
  BLINK_DURATION_MS,
  BLINK_MIN_DELAY_MS,
  EMOTE_EXIT_MS,
  ERROR_HOLD_MS,
  GAZE_RETURN_MS,
  GESTURE_DURATION_MS,
  IDLE_FLICKERS,
  IDLE_GESTURE_MAX_DELAY_MS,
  IDLE_GESTURE_MIN_DELAY_MS,
  INACTIVITY_ASLEEP_MS,
  MASK_APPLY_DELAY_MS,
  MIN_EXPRESSION_HOLD_MS,
  READING_MOVE_MS,
  READING_STEP_MS,
  SHORT_NAP_MS,
  WAKE_SHORT_PERFORMANCE,
  SACCADE_HOLD_MIN_MS,
  SACCADE_MOVE_MS,
  WAKE_PERFORMANCE,
  RETURN_PERK_MIN_AWAY_MS,
  WONDER_PERFORMANCE,
  MOOD_SHIFT_RISE_PERFORMANCE,
  WINK_DURATION_MS,
} from '../expression-engine';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import enTranslations from '../../../../locales/en/translation.json';
import frTranslations from '../../../../locales/fr/translation.json';

function renderWidget(
  props: Partial<Parameters<typeof EyesWidget>[0]> = {}
): ReturnType<typeof render> {
  const result = render(
    <EyesWidget
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
  useEyesSignalsStore.getState().reset();
  usePsycheStore.getState().reset();
  useVoiceModeStore.getState().reset();
  useVoiceModeStore.setState({ isEnabled: false, state: 'idle' });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('EyesWidget — chrome & preferences', () => {
  it('renders a focusable group with a translated name and the two eyes', () => {
    renderWidget();
    const group = screen.getByRole('group', { name: 'eyes.widget_label' });
    expect(group.tabIndex).toBe(0);
    expect(document.querySelectorAll('.lia-eye')).toHaveLength(2);
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
    fireEvent.click(screen.getByRole('button', { name: 'eyes.cycle_size' }));
    expect(eyesRoot().classList.contains('lia-eyes--md')).toBe(true);
    expect(useEyesWidgetStore.getState().size).toBe('md');
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
      rect({ left: 300, right: 400, top: 100, bottom: 140, width: 100, height: 40 })
    );
    vi.spyOn(end, 'getBoundingClientRect').mockReturnValue(
      rect({ left: 700, right: 820, top: 100, bottom: 140, width: 120, height: 40 })
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

  it('streaming answer → speaking; HITL awaiting overrides it → question', () => {
    const { rerender } = renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('speaking');
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
    act(() => {
      vi.advanceTimersByTime(INACTIVITY_ASLEEP_MS + 1500);
    });
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
    // order: silly roll, pick, pre-gaze blink roll, target x, target y, hold).
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0.9) // silly roll → no
      .mockReturnValueOnce(0) // pick → saccade
      .mockReturnValueOnce(0.9) // pre-gaze blink roll → no
      .mockReturnValueOnce(0) // target x → -0.35
      .mockReturnValueOnce(0) // target y → -0.22
      .mockReturnValueOnce(0) // hold → SACCADE_HOLD_MIN_MS
      .mockReturnValue(0.9);
    renderWidget();
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('0');
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('-0.35');
    expect(eyesRoot().style.getPropertyValue('--gaze-ms')).toBe(`${SACCADE_MOVE_MS}ms`);
    act(() => {
      vi.advanceTimersByTime(SACCADE_HOLD_MIN_MS + 10);
    });
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('0');
    expect(eyesRoot().style.getPropertyValue('--gaze-ms')).toBe(`${GAZE_RETURN_MS}ms`);
  });

  it('a wander interrupted by minimizing STILL comes home (no gaze drift, ever)', () => {
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0.9) // silly roll → no
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
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('-0.35');
    // Minimize MID-HOLD: the wander loop is torn down…
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    act(() => {
      vi.advanceTimersByTime(SACCADE_HOLD_MIN_MS + 100);
    });
    // …but the homing timer survives: restored eyes sit exactly at center.
    fireEvent.click(screen.getByRole('button', { name: 'eyes.restore' }));
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('0');
  });

  it('plays a one-shot gesture class then clears it (rng → tilt on calm)', () => {
    // Calm cumulative weights: 0.6 lands on 'tilt'.
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
    expect(eyesRoot().dataset.gesture).toBe('tilt');
    act(() => {
      vi.advanceTimersByTime(GESTURE_DURATION_MS.tilt + 10);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
  });

  it('speaking walks a reading line (the eyes write their answer, no gestures)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('speaking');
    // First reading beat: small left-to-right step, quick move, slightly up.
    act(() => {
      vi.advanceTimersByTime(READING_STEP_MS + 10);
    });
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('-0.18');
    expect(eyesRoot().style.getPropertyValue('--gaze-ms')).toBe(`${READING_MOVE_MS}ms`);
    expect(eyesRoot().dataset.gesture).toBeUndefined();
    // Second beat walks further right along the same line.
    act(() => {
      vi.advanceTimersByTime(READING_STEP_MS);
    });
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('0.2');
  });

  it('a masked change is a three-beat: blink starts, face swaps at lid-top, lids clear', () => {
    const { rerender } = renderWidget({ chatStatus: 'idle' });
    expect(eyesRoot().classList.contains('is-blinking')).toBe(false);
    rerender(<EyesWidget chatStatus="sending" streamPhase="answer" hitlAwaiting={false} />);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    // Beat 1: the lid sweep starts immediately — the face has NOT changed yet
    // (the morph happens out of sight, at the top of the blink).
    expect(eyesRoot().classList.contains('is-blinking')).toBe(true);
    expect(eyesRoot().dataset.expression).toBe('neutral');
    // Beat 2: at lid-top the new face lands.
    settleMask();
    expect(eyesRoot().dataset.expression).toBe('attentive');
    // Beat 3: the blink clears after its full cycle.
    act(() => {
      vi.advanceTimersByTime(BLINK_DURATION_MS + 10);
    });
    expect(eyesRoot().classList.contains('is-blinking')).toBe(false);
  });

  it('an idle mood flicker plays a mini scene then settles back (rng → daydream)', () => {
    // Calm cumulative weights: 0.95 lands on 'flicker'; pick 0.95 → scene #3
    // (the tender daydream), whose steps then run on the performance channel.
    vi.spyOn(Math, 'random').mockReturnValue(0.95);
    renderWidget();
    expect(eyesRoot().dataset.expression).toBe('neutral');
    act(() => {
      vi.advanceTimersByTime(
        IDLE_GESTURE_MIN_DELAY_MS +
          0.95 * (IDLE_GESTURE_MAX_DELAY_MS - IDLE_GESTURE_MIN_DELAY_MS) +
          10
      );
    });
    expect(eyesRoot().dataset.expression).toBe('tender');
    const scene = IDLE_FLICKERS[IDLE_FLICKERS.length - 1];
    act(() => {
      vi.advanceTimersByTime(scene.reduce((sum, s) => sum + s.ms, 0) + 20);
    });
    expect(eyesRoot().dataset.expression).toBe('neutral');
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

describe('EyesWidget — emotes & slapstick', () => {
  it('a HITL question floats a "?" above the eyes, and it leaves on resolution', () => {
    const { rerender } = renderWidget({ hitlAwaiting: true });
    settleMask();
    expect(document.querySelector('.lia-emote')?.textContent).toBe('?');
    rerender(<EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />);
    // The return to idle is not urgent: minimum hold first, then the masked
    // swap — the "?" starts leaving when the idle face lands.
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
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
    act(() => {
      vi.advanceTimersByTime(INACTIVITY_ASLEEP_MS + 1500);
    });
    expect(document.querySelector('.lia-emote')?.getAttribute('data-emote')).toBe('z');
  });

  it('a rare silly beat plays a slapstick gesture then clears (rng-forced swap)', () => {
    // Consumption order at mount: blink delay, idle delay; at the idle tick:
    // silly roll, silly pick. 0.01 < SILLY_PROBABILITY forces the beat.
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay → MIN
      .mockReturnValueOnce(0.01) // silly roll → yes
      .mockReturnValueOnce(0) // silly pick → swap
      .mockReturnValue(0.9);
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.gesture).toBe('swap');
    act(() => {
      vi.advanceTimersByTime(GESTURE_DURATION_MS.swap + 10);
    });
    expect(eyesRoot().dataset.gesture).toBeUndefined();
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
    // silly roll declines (0.5 > SILLY_PROBABILITY) and every gesture pick
    // lands on saccade/glance/perk, none of which touch data-expression —
    // free RNG here let a flicker steal the frame right at the settle
    // assertion (seen only on CI runners).
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    act(() => {
      // Fall asleep, then STAY asleep past the short-nap threshold: the
      // startle is earned by deep sleep, a quick doze only gets the short
      // recollection (see the short-nap test).
      vi.advanceTimersByTime(INACTIVITY_ASLEEP_MS + SHORT_NAP_MS + 1500);
    });
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
    act(() => {
      vi.advanceTimersByTime(INACTIVITY_ASLEEP_MS + 1500);
    });
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
    expect(eyesRoot().classList.contains('is-blinking')).toBe(false);
    // rng=0 → first blink exactly at BLINK_MIN_DELAY_MS.
    act(() => {
      vi.advanceTimersByTime(BLINK_MIN_DELAY_MS);
    });
    expect(eyesRoot().classList.contains('is-blinking')).toBe(true);
    act(() => {
      vi.advanceTimersByTime(BLINK_DURATION_MS);
    });
    expect(eyesRoot().classList.contains('is-blinking')).toBe(false);
    // rng=0 → double blink: second cycle after the gap.
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(eyesRoot().classList.contains('is-blinking')).toBe(true);
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

  it('a cross-family mood shift plays its rise beat while idling', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    act(() => {
      usePsycheStore.setState({ enabled: true, moodLabel: 'content' });
    });
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + 10);
    });
    act(() => {
      usePsycheStore.setState({ moodLabel: 'playful' });
    });
    act(() => {
      vi.advanceTimersByTime(10);
    });
    // First beat of MOOD_SHIFT_RISE_PERFORMANCE: an upward attentive spark.
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().style.getPropertyValue('--gaze-y')).toBe('-0.4');
    act(() => {
      vi.advanceTimersByTime(MOOD_SHIFT_RISE_PERFORMANCE[0].ms + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('joy');
  });

  it('typing that expires without a send plays the "you were saying?" wonder', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    renderWidget();
    act(() => {
      useEyesSignalsStore.getState().recordTyping();
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    // Let the typing signal expire with the chat still idle (the heartbeat
    // notices on its next second): the eyes come up from the input and
    // wonder — first the centered attentive beat, then the question.
    act(() => {
      // Past the typing TTL AND the next heartbeat tick (the beat trigger).
      vi.advanceTimersByTime(1500);
    });
    expect(eyesRoot().dataset.expression).toBe('attentive');
    expect(eyesRoot().style.getPropertyValue('--gaze-y')).toBe('0');
    act(() => {
      vi.advanceTimersByTime(WONDER_PERFORMANCE[0].ms);
    });
    expect(eyesRoot().dataset.expression).toBe('question');
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

  it('a reading line torn down by minimizing STILL comes home (no gaze drift, ever)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.9);
    renderWidget({ chatStatus: 'streaming', streamPhase: 'answer' });
    settleMask();
    act(() => {
      vi.advanceTimersByTime(READING_STEP_MS + 10);
    });
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('-0.18');
    // Minimize MID-LINE: the reading loop is torn down...
    fireEvent.click(screen.getByRole('button', { name: 'eyes.minimize' }));
    fireEvent.click(screen.getByRole('button', { name: 'eyes.restore' }));
    act(() => {
      vi.advanceTimersByTime(10);
    });
    // ...but the teardown sent the gaze home: restored eyes sit at center.
    expect(eyesRoot().style.getPropertyValue('--gaze-x')).toBe('0');
  });

  it('overlapping blink pulses never cut the lid mid-cycle (last pulse wins)', () => {
    // Force the pre-gaze blink (rng 0 < probability) on an immediate wander.
    vi.spyOn(Math, 'random')
      .mockReturnValueOnce(0.9) // blink delay (far away)
      .mockReturnValueOnce(0) // idle delay -> MIN
      .mockReturnValueOnce(0.9) // silly roll -> no
      .mockReturnValueOnce(0) // pick -> saccade
      .mockReturnValueOnce(0) // pre-gaze blink roll -> YES
      .mockReturnValue(0.9);
    renderWidget();
    act(() => {
      vi.advanceTimersByTime(IDLE_GESTURE_MIN_DELAY_MS + 10);
    });
    // The pre-gaze blink pulse is on.
    expect(eyesRoot().classList.contains('is-blinking')).toBe(true);
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
    expect(eyesRoot().classList.contains('is-blinking')).toBe(true);
    // ...and clears one full cycle after the LAST pulse, not the first.
    act(() => {
      vi.advanceTimersByTime(BLINK_DURATION_MS + 50);
    });
    expect(eyesRoot().classList.contains('is-blinking')).toBe(false);
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
    expect(eyesRoot().dataset.expression).toBe('attentive');
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
      useEyesSignalsStore.getState().setReaction('joy', Date.now());
    });
    act(() => {
      vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 10);
    });
    expect(eyesRoot().dataset.expression).toBe('joy');
    // A second, non-urgent frame right behind: it must WAIT the hold out.
    act(() => {
      useEyesSignalsStore.getState().setReaction('sad', Date.now());
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

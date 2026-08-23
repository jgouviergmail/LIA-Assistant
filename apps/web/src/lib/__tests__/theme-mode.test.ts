/**
 * Theme-mode logic — the light → dark → OLED → light cycle and its persistence.
 *
 * Kept as pure functions, away from React and from `next-themes`, because the
 * traps here are all logical rather than visual:
 *
 *  - OLED is a REFINEMENT of dark, not a fourth theme. `next-themes` keeps
 *    owning `light | dark | system`; the CSS selector is `html.dark[data-oled]`.
 *  - The cycle must start from the RESOLVED theme, not the stored one. Every
 *    new account starts at `system` (the column's `server_default`), and a
 *    `theme === 'dark' ? …` test treats `system` as "not dark" — so a user whose
 *    OS is dark clicked once and stayed dark, with nothing visibly happening.
 *  - `users.theme` is `String(20)` with no validator and no backend consumer,
 *    so `'oled'` persists with no migration. It means "dark, with OLED".
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  OLED_STORAGE_KEY,
  fromPersistedTheme,
  nextInCycle,
  toPersistedTheme,
  withThemeTransition,
} from '../theme-mode';

describe('theme-mode cycle', () => {
  it('goes light → dark', () => {
    expect(nextInCycle('light', false)).toEqual({ mode: 'dark', oled: false });
  });

  it('goes dark → OLED', () => {
    expect(nextInCycle('dark', false)).toEqual({ mode: 'dark', oled: true });
  });

  it('closes the circle OLED → light', () => {
    expect(nextInCycle('dark', true)).toEqual({ mode: 'light', oled: false });
  });

  it('completes a full turn in exactly three steps', () => {
    let state = { mode: 'light' as const, oled: false };
    const seen: string[] = [];
    for (let i = 0; i < 3; i++) {
      const next = nextInCycle(state.mode === 'light' ? 'light' : 'dark', state.oled);
      seen.push(`${next.mode}${next.oled ? '+oled' : ''}`);
      state = next as typeof state;
    }
    expect(seen).toEqual(['dark', 'dark+oled', 'light']);
  });

  it('leaves OLED behind when it returns to light', () => {
    // Light mode cannot express OLED — the CSS selector requires `.dark` — so
    // carrying the flag would make the NEXT click land on dark+OLED, skipping
    // plain dark and breaking the circle.
    expect(nextInCycle('dark', true).oled).toBe(false);
  });

  it('starts from the resolved theme, so a system-dark user advances visibly', () => {
    // The pre-existing bug: `theme` is 'system', `resolvedTheme` is 'dark'.
    // Reading `theme` would send them to 'dark' — no visible change at all.
    expect(nextInCycle('dark', false)).toEqual({ mode: 'dark', oled: true });
  });

  it('treats an unresolved theme as light rather than throwing', () => {
    // Before mount `resolvedTheme` is undefined; the control must still work.
    expect(nextInCycle(undefined, false)).toEqual({ mode: 'dark', oled: false });
  });
});

describe('theme-mode persistence', () => {
  it('persists OLED as its own theme value', () => {
    expect(toPersistedTheme({ mode: 'dark', oled: true })).toBe('oled');
  });

  it('persists the plain modes unchanged', () => {
    expect(toPersistedTheme({ mode: 'light', oled: false })).toBe('light');
    expect(toPersistedTheme({ mode: 'dark', oled: false })).toBe('dark');
    expect(toPersistedTheme({ mode: 'system', oled: false })).toBe('system');
  });

  it('never persists OLED against a mode that cannot render it', () => {
    // Defensive: OLED implies dark. A light+oled pair must not round-trip into
    // a stored 'oled' that would silently flip the user to dark on next load.
    expect(toPersistedTheme({ mode: 'light', oled: true })).toBe('light');
    expect(toPersistedTheme({ mode: 'system', oled: true })).toBe('system');
  });

  it('reads OLED back as dark + the flag', () => {
    expect(fromPersistedTheme('oled')).toEqual({ mode: 'dark', oled: true });
  });

  it('reads the plain modes back unchanged', () => {
    expect(fromPersistedTheme('light')).toEqual({ mode: 'light', oled: false });
    expect(fromPersistedTheme('dark')).toEqual({ mode: 'dark', oled: false });
    expect(fromPersistedTheme('system')).toEqual({ mode: 'system', oled: false });
  });

  it('falls back to system for absent or unknown values', () => {
    // `users.theme` has no Literal and no validator: anything can be in there,
    // including a value written by a future version.
    expect(fromPersistedTheme(null)).toEqual({ mode: 'system', oled: false });
    expect(fromPersistedTheme(undefined)).toEqual({ mode: 'system', oled: false });
    expect(fromPersistedTheme('sepia')).toEqual({ mode: 'system', oled: false });
    expect(fromPersistedTheme('')).toEqual({ mode: 'system', oled: false });
  });

  it('round-trips every reachable state', () => {
    for (const state of [
      { mode: 'light' as const, oled: false },
      { mode: 'dark' as const, oled: false },
      { mode: 'dark' as const, oled: true },
      { mode: 'system' as const, oled: false },
    ]) {
      expect(fromPersistedTheme(toPersistedTheme(state))).toEqual(state);
    }
  });

  it('fits the String(20) column it is stored in', () => {
    for (const v of ['light', 'dark', 'system', 'oled']) expect(v.length).toBeLessThanOrEqual(20);
  });

  it('keeps its storage key distinct from the next-themes one', () => {
    // next-themes owns 'theme'; clobbering it would fight the provider.
    expect(OLED_STORAGE_KEY).not.toBe('theme');
  });
});

describe('withThemeTransition', () => {
  // lib.dom types `startViewTransition` as always present, so the stubs go
  // through an index signature rather than fighting a type that does not match
  // the browsers this guard exists for.
  const doc = document as unknown as Record<string, unknown>;

  afterEach(() => {
    delete doc.startViewTransition;
    vi.restoreAllMocks();
  });

  /** Pretend the browser supports view transitions, and report whether it was used. */
  function stubViewTransition() {
    const start = vi.fn((cb: () => void) => {
      cb();
      return { ready: Promise.resolve() };
    });
    doc.startViewTransition = start;
    return start;
  }

  /** Force the reduced-motion media query one way or the other. */
  function stubReducedMotion(matches: boolean) {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches,
      media: '(prefers-reduced-motion: reduce)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList);
  }

  it('applies the change on a browser without the API', () => {
    stubReducedMotion(false);
    const apply = vi.fn();
    withThemeTransition(apply, { x: 10, y: 10 });
    // Firefox and older Safari must still get their theme — progressive
    // enhancement, never a dependency.
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('uses the view transition when the browser has one', () => {
    stubReducedMotion(false);
    const start = stubViewTransition();
    const apply = vi.fn();
    withThemeTransition(apply, { x: 10, y: 10 });
    expect(start).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('skips the animation entirely under prefers-reduced-motion', () => {
    stubReducedMotion(true);
    const start = stubViewTransition();
    const apply = vi.fn();
    withThemeTransition(apply, { x: 10, y: 10 });
    // A full-viewport wipe is precisely the large-area motion that setting
    // exists to suppress — the theme still changes, instantly.
    expect(start).not.toHaveBeenCalled();
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('still transitions without an origin, just without the circular reveal', () => {
    stubReducedMotion(false);
    const start = stubViewTransition();
    const apply = vi.fn();
    withThemeTransition(apply);
    expect(start).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('applies the change synchronously inside the callback', () => {
    // The API snapshots before and after the callback; an async mutation would
    // be captured in neither frame.
    stubReducedMotion(false);
    let appliedDuringCallback = false;
    doc.startViewTransition = (cb: () => void) => {
      cb();
      appliedDuringCallback = true;
      return { ready: Promise.resolve() };
    };
    let applied = false;
    withThemeTransition(() => {
      applied = true;
    });
    expect(applied).toBe(true);
    expect(appliedDuringCallback).toBe(true);
  });

  it('survives a matchMedia-less environment', () => {
    const original = window.matchMedia;
    // @ts-expect-error deliberately removing the API to prove the fallback
    delete window.matchMedia;
    try {
      const apply = vi.fn();
      expect(() => withThemeTransition(apply)).not.toThrow();
      expect(apply).toHaveBeenCalledTimes(1);
    } finally {
      window.matchMedia = original;
    }
  });
});

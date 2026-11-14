/**
 * The header's circle walked press after press, on the REAL `next-themes` provider
 * and an account a server really answers with.
 *
 * The other suites of the circle hold `next-themes` still and judge one press at a
 * time. Two defects only show on a walk, where the theme really changes and the
 * account is really read back (owner report 2026-11-14, ADR-243 follow-up):
 *
 *  - a change drawn AHEAD of its reveal is not revealed: the reveal photographs the
 *    page, runs the change, photographs it again, so what was drawn before the first
 *    photograph snaps. Entering automatic by day did, its clock drawing first;
 *  - a press UNDONE by the account: the provider's `setTheme` is a new function at
 *    every theme change, and an effect listing it ran again on the press itself,
 *    redrawing whatever the account still said.
 */
import { useSyncExternalStore } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';

vi.unmock('next-themes');

/** The frame after which the engine runs a reveal's change. */
const FRAME_MS = 16;
/** A server that takes longer than a frame, as one across a network does. */
const SLOW_MS = 40;
/** One beat of the walk: React settles between two of them, as it does between two tasks. */
const BEAT_MS = 8;
/** Long enough for a press to be drawn, saved and read back. */
const SETTLED_MS = FRAME_MS + 2 * SLOW_MS + 3 * BEAT_MS;

type Account = Record<string, unknown>;

const world = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const state = {
    user: null as Record<string, unknown> | null,
    server: null as Record<string, unknown> | null,
    /** How long a save takes, and how long the read that follows it. */
    saveMs: 0,
    readMs: 0,
    /** The account cannot be written: every save fails. */
    offline: false,
  };
  let snapshot = state.user;
  return {
    state,
    publish: () => {
      snapshot = state.user;
      listeners.forEach(listener => listener());
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read: () => snapshot,
    wait: (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)),
  };
});

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: useSyncExternalStore(world.subscribe, world.read, world.read),
    isLoading: false,
    refreshUser: async () => {
      await world.wait(world.state.readMs);
      world.state.user = { ...world.state.server };
      world.publish();
      return true;
    },
  }),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({
    mutate: async (_path: string, patch: Account) => {
      await world.wait(world.state.saveMs);
      if (world.state.offline) throw new Error('offline');
      world.state.server = { ...world.state.server, ...patch };
      return world.state.server;
    },
  }),
}));

import { ThemeProvider } from '@/components/theme-provider';
import { ThemeModeProvider } from '@/lib/theme-preferences';
import { ThemeToggle } from '../theme-toggle';

type Picture = 'light' | 'dark' | 'OLED';

/** What the page shows, read where the stylesheet reads it. */
function picture(): Picture {
  const root = document.documentElement;
  if (!root.classList.contains('dark')) return 'light';
  return root.hasAttribute('data-oled') ? 'OLED' : 'dark';
}

/** An account whose automatic mode shows the day, or the night, at any hour but one minute. */
function account(theme: string, night: boolean): Account {
  return {
    id: 'owner',
    theme,
    timezone: 'Europe/Paris',
    theme_light_start_minute: night ? 1439 : 0,
    theme_dark_start_minute: night ? 0 : 1439,
  };
}

/** The pictures the page went through, and what each reveal photographed first. */
interface Film {
  shown: Picture[];
  photographed: Picture[];
  stop: () => void;
}

/**
 * Films the page and stands in for the engine's reveal: the page is photographed
 * at the frame AFTER the call, and only then does the change run.
 */
function film(): Film {
  const shown: Picture[] = [];
  const photographed: Picture[] = [];
  const observer = new MutationObserver(() => {
    if (shown.at(-1) !== picture()) shown.push(picture());
  });
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-oled'],
  });
  Object.defineProperty(document, 'startViewTransition', {
    configurable: true,
    value: (change: () => void) => {
      setTimeout(() => {
        photographed.push(picture());
        change();
      }, FRAME_MS);
      return { ready: new Promise<void>(() => {}) };
    },
  });
  return { shown, photographed, stop: () => observer.disconnect() };
}

/** Lets the page live for a while, React settling at every beat. */
async function settle(): Promise<void> {
  for (let elapsed = 0; elapsed < SETTLED_MS; elapsed += BEAT_MS) {
    await act(async () => {
      await world.wait(BEAT_MS);
    });
  }
}

/** The application's own provider settings (`app/[lng]/layout.tsx`). */
function mountCircle(start: Account) {
  world.state.server = start;
  world.state.user = { ...start };
  world.publish();
  return renderWithProviders(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
      <ThemeModeProvider>
        <ThemeToggle />
      </ThemeModeProvider>
    </ThemeProvider>
  );
}

const toggle = () => screen.getByRole('button');

let filming: Film | undefined;
beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-oled');
  document.documentElement.classList.remove('dark', 'light');
  Object.assign(world.state, { saveMs: SLOW_MS, readMs: SLOW_MS, offline: false });
});
afterEach(() => {
  filming?.stop();
  Reflect.deleteProperty(document, 'startViewTransition');
});

describe.each([
  ['a server slower than a frame', SLOW_MS, SLOW_MS],
  ['a save answered within the frame', 0, SLOW_MS],
  ['a save and its read answered within the frame', 0, 0],
])('the circle walked with %s', (_server, saveMs, readMs) => {
  describe.each([
    ['by day', false],
    ['by night', true],
  ])('%s', (_hour, night) => {
    it.each(['light', 'auto'])(
      'reveals every change, and none is undone, from an account on %s',
      async start => {
        Object.assign(world.state, { saveMs, readMs });
        const { user } = mountCircle(account(start, night));
        await settle();
        filming = film();
        const { shown, photographed } = filming;

        const saved: unknown[] = [];
        // A whole lap and one press more: every stop is entered and left.
        for (let press = 1; press <= 5; press += 1) {
          const before = picture();
          const destination = toggle().getAttribute('aria-label');
          shown.length = 0;
          await user.click(toggle());
          await settle();
          const told = `press ${press} (${destination}), from ${before}`;
          // Nothing drew the change ahead of its reveal…
          expect(photographed, told).toHaveLength(press);
          expect(photographed[press - 1], told).toBe(before);
          // …and the page never came back to a picture it had left.
          const walked = [before, ...shown];
          expect(new Set(walked).size, `${told}: ${walked.join(' → ')}`).toBe(walked.length);
          saved.push(world.state.server?.theme);
        }

        // The circle is the one Settings lists, wherever the walk started.
        const lap = ['light', 'dark', 'oled', 'auto'];
        const first = lap.indexOf(String(saved[0]));
        expect(saved).toEqual(saved.map((_, index) => lap[(first + index) % lap.length]));
      }
    );
  });
});

describe('the circle walked without its server', () => {
  it('holds automatic on the press alone: the next press leaves it for light', async () => {
    // By night automatic shows the black just left, so only the MODE says where the
    // circle stands. Read back from the account alone, an unsaved automatic would be
    // taken for OLED and the next press would enter it again, for ever.
    world.state.offline = true;
    const { user } = mountCircle(account('oled', true));
    await settle();
    expect(picture()).toBe('OLED');
    expect(toggle()).toHaveAccessibleName('theme.to_auto');

    await user.click(toggle());
    await settle();
    expect(world.state.server?.theme).toBe('oled');
    expect(picture()).toBe('OLED');
    expect(toggle()).toHaveAccessibleName('theme.to_light');

    await user.click(toggle());
    await settle();
    expect(picture()).toBe('light');
    expect(toggle()).toHaveAccessibleName('theme.to_dark');
  });
});

describe('the circle beside another tab of the same account', () => {
  it('follows the other tab instead of answering it with what the account said', async () => {
    // The other tab chose dark: `next-themes` shares the choice through storage, and
    // this tab's account still says light until it is read again. Redrawing the
    // account here wrote light back to the shared storage, and the two tabs threw
    // the theme at each other.
    mountCircle(account('light', false));
    await settle();
    expect(picture()).toBe('light');

    localStorage.setItem('theme', 'dark');
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'theme', newValue: 'dark' }));
    });
    await settle();

    expect(picture()).toBe('dark');
    expect(localStorage.getItem('theme')).toBe('dark');
  });
});

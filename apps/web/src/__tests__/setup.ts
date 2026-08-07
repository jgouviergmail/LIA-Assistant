/**
 * Vitest Setup File
 *
 * Configures test environment with:
 * - jest-dom matchers for DOM assertions
 * - Mocks for Next.js router
 * - i18n mock for translations
 *
 * LOT 10: Frontend Tests for LOT 8 Modal Edit
 */

import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock Next.js router
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

// STABLE translation stub — built ONCE and shared by both i18n mocks below.
//
// Identity stability is not cosmetic here: a hook mock that hands back a fresh
// `t` on every call re-triggers every effect depending on it. A component that
// holds `t` in a `useCallback`/`useEffect` dependency array (e.g.
// `AdminUsersSection`'s fetch effect) then spins in an infinite
// render → fetch → render loop and the test hangs instead of failing. The real
// `useTranslation` memoizes `t` through react-i18next, so pinning the identity
// here is what makes the mock faithful rather than merely convenient
// (GUIDE_TESTING → Pièges connus, « stabilité des mocks de hooks »).
const { i18nStub } = vi.hoisted(() => ({
  i18nStub: {
    t: (key: string) => key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  },
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => i18nStub,
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: {
    type: '3rdParty',
    init: vi.fn(),
  },
}));

// Mock the app's client-side i18n wrapper (`@/i18n/client`).
// 67 client components consume `useTranslation` from this module instead of
// `react-i18next` directly. The real wrapper spins up a live i18next instance
// in a `useEffect` (dynamic `import()` of locale JSON) — a non-deterministic
// side effect in jsdom. Mocking it here mirrors the `react-i18next` mock above
// (`t` echoes the key) so every consumer renders deterministically with zero
// network/timer side effects. A test can still override this per-file with its
// own `vi.mock('@/i18n/client', ...)` when it needs bespoke translations.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => i18nStub,
}));

// Mock next-themes. The real `ThemeProvider` injects an inline anti-FOUC
// `<script>` into the tree (it pollutes `container` in tests) and reads
// `matchMedia`/`localStorage` on mount. Replacing it with a passthrough plus a
// deterministic `useTheme` keeps rendered output clean and stable for the ~6
// components that branch on the resolved theme. A test can still override the
// resolved theme per-file with its own `vi.mock('next-themes', ...)`.
vi.mock('next-themes', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => children,
  useTheme: () => ({
    theme: 'light',
    resolvedTheme: 'light',
    systemTheme: 'light',
    themes: ['light', 'dark'],
    setTheme: vi.fn(),
  }),
}));

// Mock window.matchMedia
// Guarded: test files may opt into `@vitest-environment node` (e.g. to cover
// SSR branches where `typeof window === 'undefined'`); this setup file runs
// for every environment.
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// `scrollIntoView` does not exist in jsdom — it has no layout to scroll. The
// same gap as ResizeObserver below, so it is filled the same way: once, here,
// rather than in every suite that renders a component which follows its own
// content. Deliberately an inert no-op and NOT a shared `vi.fn()`: a shared spy
// accumulates calls across tests, so a suite asserting a call count would read
// its neighbours'. Tests that need to observe it install their own spy (see
// `SlashCommandMenu.test.tsx`, `useFollowLatest.test.tsx`).
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView(): void {};
}

// Mock ResizeObserver / IntersectionObserver as real CLASS constructors (not
// `vi.fn(() => ({...}))`): floating-ui's `autoUpdate` (used by Radix Tooltip /
// Select / Popover / DropdownMenu positioning) does `new ResizeObserver(...)`
// on a code path that rejects a plain-object-returning mock with
// "X is not a constructor", surfacing as an intermittent uncaught exception.
// Classes satisfy it and let those Radix primitives open in tests.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
global.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

// Constructor arguments are ACCEPTED and reflected, unlike a bare default
// constructor: production code calls `new IntersectionObserver(cb, { rootMargin })`,
// and a stub that takes none made every such call read as passing superfluous
// arguments (7 CodeQL js/superfluous-trailing-arguments alerts) while silently
// dropping the callback — which is why `ChatMessageList.test.tsx` had to ship its
// own observer double to test anything.
//
// The callback is stored, never invoked: nothing here fires an intersection on
// its own. Components that only act when their sentinel scrolls into view
// (AnimatedCounter, FadeInOnScroll, ChapterRail…) therefore keep the exact
// behaviour they had under the old stub. A test that WANTS an intersection
// installs its own double via `vi.stubGlobal`.
class IntersectionObserverStub implements IntersectionObserver {
  readonly root: Element | Document | null;
  readonly rootMargin: string;
  readonly scrollMargin: string;
  readonly thresholds: ReadonlyArray<number>;

  constructor(
    readonly callback: IntersectionObserverCallback,
    options?: IntersectionObserverInit
  ) {
    this.root = options?.root ?? null;
    this.rootMargin = options?.rootMargin ?? '';
    this.scrollMargin = options?.scrollMargin ?? '';
    this.thresholds = options?.threshold === undefined ? [] : [options.threshold].flat();
  }

  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
global.IntersectionObserver = IntersectionObserverStub;

// jsdom lacks the pointer-capture and scroll APIs that Radix primitives
// (DropdownMenu, Select, Popover…) call when opening/closing. Stub them so those
// components can be exercised in tests instead of throwing.
if (typeof window !== 'undefined') {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = vi.fn();
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
}

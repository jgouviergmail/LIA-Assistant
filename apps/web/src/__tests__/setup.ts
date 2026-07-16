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

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'fr',
      changeLanguage: vi.fn(),
    },
  }),
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
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'fr',
      changeLanguage: vi.fn(),
    },
  }),
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

class IntersectionObserverStub {
  readonly root = null;
  readonly rootMargin = '';
  readonly thresholds: ReadonlyArray<number> = [];
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
global.IntersectionObserver = IntersectionObserverStub as unknown as typeof IntersectionObserver;

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

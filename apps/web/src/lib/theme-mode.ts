/**
 * The display-mode state machine: light → dark → OLED → light.
 *
 * OLED is a REFINEMENT of dark, never a fourth theme. `next-themes` keeps
 * owning `light | dark | system` and keeps setting `.dark`; OLED is a separate
 * `data-oled` attribute on `<html>`, selected by `html.dark[data-oled]`.
 *
 * That split is not cosmetic. Making OLED a third `next-themes` value would set
 * `class="oled"` INSTEAD of `class="dark"` (the provider calls
 * `classList.add(v)` with a single value, so a `"dark oled"` mapping throws),
 * which would silently flip 9 `resolvedTheme === 'dark'` call sites to their
 * light branch — light syntax highlighting on a black page, white Mermaid
 * diagrams, invisible snowflakes — and send the 9 `html:not(.dark) .cosmos`
 * rules down their light branch across the whole public site.
 *
 * Keeping `.dark` also keeps `color-scheme: dark` (declared in the `.dark`
 * block) applying, so native selects and scrollbars stay dark. `next-themes`
 * only sets `style.colorScheme` for values in its `colorSchemes` list, so a
 * third value would have left it stale.
 */

/** Display modes `next-themes` itself understands. */
export type DisplayMode = 'light' | 'dark' | 'system';

/** Full display state: a mode, plus the OLED refinement of dark. */
export interface ThemeModeState {
  mode: DisplayMode;
  oled: boolean;
}

/**
 * localStorage key for the OLED flag.
 *
 * Deliberately NOT `theme`: that one belongs to `next-themes`, and writing it
 * would fight the provider on every render.
 */
export const OLED_STORAGE_KEY = 'theme-oled';

/** The persisted values `users.theme` may hold. */
const PERSISTED = new Set(['light', 'dark', 'system', 'oled']);

/**
 * Encode the state for `users.theme`.
 *
 * The column is `String(20)`, `nullable=False`, with no `Literal`, no validator
 * and no backend consumer, so `'oled'` needs no migration. It means "dark, with
 * OLED": `system + OLED` is deliberately not representable, because OLED is an
 * explicit choice rather than something to inherit from the OS at dusk.
 */
export function toPersistedTheme({ mode, oled }: ThemeModeState): string {
  // OLED implies dark. Persisting it against any other mode would silently
  // move the user on their next load.
  return oled && mode === 'dark' ? 'oled' : mode;
}

/**
 * Decode `users.theme` back into a state.
 *
 * Unknown values fall back to `system` — the column's own `server_default`, and
 * therefore what every account starts on.
 */
export function fromPersistedTheme(value: string | null | undefined): ThemeModeState {
  if (!value || !PERSISTED.has(value)) return { mode: 'system', oled: false };
  if (value === 'oled') return { mode: 'dark', oled: true };
  return { mode: value as DisplayMode, oled: false };
}

/**
 * The next state in the header's circular toggle.
 *
 * Driven by the RESOLVED theme, never the stored one: every account starts at
 * `system`, and a `theme === 'dark'` test classifies that as "not dark", so a
 * user whose OS is dark used to click and see nothing change.
 *
 * Returning to light clears the OLED flag, otherwise the following click would
 * land straight back on dark+OLED and skip plain dark — the circle would have
 * two states instead of three.
 */
export function nextInCycle(
  resolved: 'light' | 'dark' | undefined,
  oled: boolean
): { mode: 'light' | 'dark'; oled: boolean } {
  // Narrower than `ThemeModeState` on purpose: the cycle never lands on
  // `system`, and saying so lets callers index a three-entry table without a
  // fourth, unreachable branch.
  if (resolved !== 'dark') return { mode: 'dark', oled: false };
  return oled ? { mode: 'light', oled: false } : { mode: 'dark', oled: true };
}

/**
 * Apply the OLED flag to `<html>` without animating the whole page into it.
 *
 * `next-themes`' `disableTransitionOnChange` only wraps its OWN `setTheme`, and
 * the dark → OLED step never calls it (the theme stays `dark`, only the
 * attribute changes). Without this, every element carrying a colour transition
 * would animate to black at once. The technique mirrors the provider's: inject
 * a blanket `transition: none`, force a reflow so it is actually in effect,
 * then drop it on the next tick.
 */
export function applyOledAttribute(oled: boolean): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const style = document.createElement('style');
  style.appendChild(
    document.createTextNode('*,*::before,*::after{transition:none!important;animation:none!important}')
  );
  document.head.appendChild(style);

  if (oled) root.setAttribute('data-oled', '');
  else root.removeAttribute('data-oled');

  // Force a reflow so the blanket rule is genuinely in effect before it is
  // removed; without it the browser may coalesce both mutations and animate
  // anyway. Wrapped in an IIFE — the same shape `next-themes` uses — so the
  // read is a call expression rather than a bare expression statement.
  (() => window.getComputedStyle(document.body))();
  window.setTimeout(() => style.remove(), 1);
}

/** A point on screen, in client coordinates. */
export interface TransitionOrigin {
  x: number;
  y: number;
}

/** Longest distance from `origin` to a corner — the radius that covers the viewport. */
function radiusToFurthestCorner({ x, y }: TransitionOrigin): number {
  return Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
}

/**
 * Run a theme change as a circular reveal from the control that triggered it.
 *
 * Three guards, in order, and each one matters:
 *  - `prefers-reduced-motion` skips the animation entirely. A full-viewport
 *    wipe is exactly the kind of large-area motion that setting exists for.
 *  - `startViewTransition` is feature-detected, so Firefox and older Safari get
 *    the instant swap they get today — a progressive enhancement, never a
 *    dependency.
 *  - No origin (keyboard activation, programmatic change) falls back to the
 *    browser's own cross-fade rather than picking an arbitrary centre.
 *
 * The callback MUST apply the change synchronously: the API snapshots the page
 * before it runs and again after, and an async mutation would be captured in
 * neither frame.
 */
export function withThemeTransition(apply: () => void, origin?: TransitionOrigin): void {
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

  // `startViewTransition` is typed as always present by lib.dom, but it is not:
  // Firefox and older Safari ship no implementation, so the runtime check is
  // the real one and the type says nothing useful here.
  if (reduced || typeof document.startViewTransition !== 'function') {
    apply();
    return;
  }

  const transition = document.startViewTransition(apply);
  if (!origin) return;

  transition.ready
    .then(() => {
      const radius = radiusToFurthestCorner(origin);
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${origin.x}px ${origin.y}px)`,
            `circle(${radius}px at ${origin.x}px ${origin.y}px)`,
          ],
        },
        {
          duration: 420,
          easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
          pseudoElement: '::view-transition-new(root)',
        }
      );
    })
    .catch(() => {
      // The transition can be skipped (a second click, a navigation) — the
      // theme itself has already been applied by the callback, so there is
      // nothing to recover and nothing worth logging.
    });
}

/** Read the persisted OLED flag, tolerating storage being unavailable. */
export function readStoredOled(): boolean {
  try {
    return window.localStorage.getItem(OLED_STORAGE_KEY) === '1';
  } catch {
    // Private mode / storage disabled: OLED is a preference, not a necessity.
    return false;
  }
}

/** Persist the OLED flag, tolerating storage being unavailable. */
export function writeStoredOled(oled: boolean): void {
  try {
    window.localStorage.setItem(OLED_STORAGE_KEY, oled ? '1' : '0');
  } catch {
    // Same rationale as `readStoredOled`.
  }
}

/**
 * Font configuration for the application.
 *
 * Every face is SELF-HOSTED via next/font/local from woff2 files committed
 * under src/fonts/ (latin subset, the exact static instances Google Fonts
 * served for the previous next/font/google config — same families, same
 * weights, same CSS variables, so rendering is unchanged).
 *
 * Why not next/font/google: it downloads fonts from fonts.gstatic.com at
 * BUILD time, and Google rotates hosted file versions — two production
 * image builds failed on 2026-08-16 with 404s on freshly rotated URLs
 * (28 Turbopack errors each). A production build must not depend on a
 * third-party CDN being consistent mid-rotation. Geist already ships from
 * its npm package.
 *
 * Guard: src/lib/__tests__/fonts.test.ts pins the no-network contract
 * (no next/font/google import may reappear) and the exported variables.
 */

// preload: false on every family below — these are USER-SELECTABLE display
// fonts, applied one at a time through `data-font`. Preloading them all made
// the browser fetch 26 font files (618 KB, measured 2026-08-23) on a page that
// renders only Inter. Next still emits the @font-face rules, so the family the
// user actually picked loads on demand, exactly like any other webfont. Inter
// itself is declared in layout.tsx and stays preloaded: it IS the default.

import localFont from 'next/font/local';
import { GeistSans } from 'geist/font/sans';

export const notoSans = localFont({
  src: [
    { path: '../fonts/noto-sans/noto-sans-400.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/noto-sans/noto-sans-500.woff2', weight: '500', style: 'normal' },
    { path: '../fonts/noto-sans/noto-sans-600.woff2', weight: '600', style: 'normal' },
    { path: '../fonts/noto-sans/noto-sans-700.woff2', weight: '700', style: 'normal' },
  ],
  preload: false,
  variable: '--font-noto-sans',
  display: 'swap',
});

export const plusJakartaSans = localFont({
  src: [
    {
      path: '../fonts/plus-jakarta-sans/plus-jakarta-sans-400.woff2',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../fonts/plus-jakarta-sans/plus-jakarta-sans-500.woff2',
      weight: '500',
      style: 'normal',
    },
    {
      path: '../fonts/plus-jakarta-sans/plus-jakarta-sans-600.woff2',
      weight: '600',
      style: 'normal',
    },
    {
      path: '../fonts/plus-jakarta-sans/plus-jakarta-sans-700.woff2',
      weight: '700',
      style: 'normal',
    },
  ],
  preload: false,
  variable: '--font-plus-jakarta',
  display: 'swap',
});

export const ibmPlexSans = localFont({
  src: [
    { path: '../fonts/ibm-plex-sans/ibm-plex-sans-400.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/ibm-plex-sans/ibm-plex-sans-500.woff2', weight: '500', style: 'normal' },
    { path: '../fonts/ibm-plex-sans/ibm-plex-sans-600.woff2', weight: '600', style: 'normal' },
    { path: '../fonts/ibm-plex-sans/ibm-plex-sans-700.woff2', weight: '700', style: 'normal' },
  ],
  preload: false,
  variable: '--font-ibm-plex',
  display: 'swap',
});

export const sourceSans3 = localFont({
  src: [
    { path: '../fonts/source-sans-3/source-sans-3-400.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/source-sans-3/source-sans-3-500.woff2', weight: '500', style: 'normal' },
    { path: '../fonts/source-sans-3/source-sans-3-600.woff2', weight: '600', style: 'normal' },
    { path: '../fonts/source-sans-3/source-sans-3-700.woff2', weight: '700', style: 'normal' },
  ],
  preload: false,
  variable: '--font-source-sans',
  display: 'swap',
});

export const merriweather = localFont({
  src: [
    { path: '../fonts/merriweather/merriweather-400.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/merriweather/merriweather-700.woff2', weight: '700', style: 'normal' },
  ],
  preload: false,
  variable: '--font-merriweather',
  display: 'swap',
});

export const libreBaskerville = localFont({
  src: [
    {
      path: '../fonts/libre-baskerville/libre-baskerville-400.woff2',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../fonts/libre-baskerville/libre-baskerville-700.woff2',
      weight: '700',
      style: 'normal',
    },
  ],
  preload: false,
  variable: '--font-libre-baskerville',
  display: 'swap',
});

export const firaCode = localFont({
  src: [
    { path: '../fonts/fira-code/fira-code-400.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/fira-code/fira-code-500.woff2', weight: '500', style: 'normal' },
    { path: '../fonts/fira-code/fira-code-700.woff2', weight: '700', style: 'normal' },
  ],
  preload: false,
  variable: '--font-fira-code',
  display: 'swap',
});

// Geist from npm package (Vercel's font)
export const geistSans = GeistSans;

/**
 * The icons of the PUBLIC pages: Material Symbols Outlined cut down to the few
 * icons they draw (the landing's demo), ~4 KB where the full variable font the
 * application loads from Google Fonts is 4 MB — and the landing used to download
 * it before the reader scrolled (measured 2026-10-28). `lia-components.css` maps
 * `.landing-page .material-symbols-outlined` to this family, so the full font is
 * never requested there; the application keeps it, because the cards the model
 * writes may name any icon. Written by `scripts/build-public-icon-font.mjs`, held
 * to what public pages draw by `__tests__/public-icon-font.guard.test.ts`.
 *
 * `display: 'block'`: an icon font in `swap` shows its ligature NAMES
 * ("check_circle") while it loads. No metric-adjusted fallback: a system face
 * shaped like this one does not exist.
 */
export const publicSymbols = localFont({
  src: [
    {
      path: '../fonts/material-symbols-public/material-symbols-public.woff2',
      weight: '400',
      style: 'normal',
    },
  ],
  preload: false,
  variable: '--font-public-symbols',
  display: 'block',
  adjustFontFallback: false,
});

// Combined class names for layout.tsx
export const fontVariables = [
  notoSans.variable,
  plusJakartaSans.variable,
  ibmPlexSans.variable,
  sourceSans3.variable,
  merriweather.variable,
  libreBaskerville.variable,
  firaCode.variable,
  geistSans.variable,
  publicSymbols.variable,
].join(' ');

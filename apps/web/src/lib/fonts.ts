/**
 * Font configuration for the application.
 *
 * Uses next/font/google for optimal loading (self-hosted, no CLS, no FOUT).
 * Geist is loaded from the npm package.
 */

import {
  Fira_Code,
  IBM_Plex_Sans,
  Libre_Baskerville,
  Merriweather,
  Noto_Sans,
  Plus_Jakarta_Sans,
  Source_Sans_3,
} from 'next/font/google';
import { GeistSans } from 'geist/font/sans';

// Google Fonts with CSS variables
export const notoSans = Noto_Sans({
  subsets: ['latin'],
  variable: '--font-noto-sans',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
});

export const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-plus-jakarta',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
});

export const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  variable: '--font-ibm-plex',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
});

export const sourceSans3 = Source_Sans_3({
  subsets: ['latin'],
  variable: '--font-source-sans',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
});

export const merriweather = Merriweather({
  subsets: ['latin'],
  variable: '--font-merriweather',
  display: 'swap',
  weight: ['400', '700'],
});

export const libreBaskerville = Libre_Baskerville({
  subsets: ['latin'],
  variable: '--font-libre-baskerville',
  display: 'swap',
  weight: ['400', '700'],
});

export const firaCode = Fira_Code({
  subsets: ['latin'],
  variable: '--font-fira-code',
  display: 'swap',
  weight: ['400', '500', '700'],
});

// Geist from npm package (Vercel's font)
export const geistSans = GeistSans;

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
].join(' ');

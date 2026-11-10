import { SelectionAssistProvider } from '@/components/selection-assist/SelectionAssistProvider';
/**
 * Language-specific layout
 *
 * This is the ROOT layout for the application.
 * It wraps all pages with i18n context and application providers.
 * Receives the language parameter from the URL.
 */

import { type ReactNode } from 'react';
import type { Metadata, Viewport } from 'next';
import localFont from 'next/font/local';
import { AuthProvider } from '@/lib/auth';
import { ServiceWorkerRegistration } from '@/components/ServiceWorkerRegistration';
import { PresencePing } from '@/components/telemetry/PresencePing';
import { TelemetryBootstrap } from '@/components/telemetry/TelemetryBootstrap';
import { QueryProvider } from '@/lib/query-client';
import { LoggingProvider } from '@/lib/logging-context';
import { ThemeProvider } from '@/components/theme-provider';
import { ThemeModeProvider } from '@/lib/theme-preferences';
import { ThemeInitScript } from '@/components/theme-init-script';
import { ColorThemeProvider } from '@/lib/theme-context';
import { IconStyleProvider } from '@/components/settings/IconStyleProvider';
import { FontProvider } from '@/lib/font-context';
import { FontPreferencesSync } from '@/components/settings/FontPreferencesSync';
import { ColorPreferencesSync } from '@/components/settings/ColorPreferencesSync';
import { TranslationsProvider } from '@/components/TranslationsProvider';
import { ApplicationLocaleSync } from '@/components/ApplicationLocaleSync';
import { fontVariables } from '@/lib/fonts';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { SnowfallEffect } from '@/components/effects/SnowfallEffect';
import { LandingVideoHostSection } from '@/components/landing/video/LandingVideoHostSection';
import { defaultNS, languages } from '@/i18n/settings';
import { translationBundle, validateLanguage } from '@/i18n';
import { ROUTE_SCOPED_TRANSLATIONS, omitTranslations } from '@/i18n/scoped-translations';
import { WebSiteJsonLd, OrganizationJsonLd } from '@/components/seo/JsonLd';
import { buildAppMetadata } from '@/lib/app-metadata';
import '@/styles/globals.css';
import 'katex/dist/katex.min.css';

// Use local Inter font to avoid network dependency during Docker build
const inter = localFont({
  src: '../../../public/fonts/Inter-Variable.woff2',
  variable: '--font-inter',
  display: 'swap',
  weight: '100 900',
});

/**
 * Per-locale metadata (UXR Lot 9, A6) — the factory lives in
 * `lib/app-metadata.ts` (pure, unit-guarded); this wrapper only resolves the
 * validated locale from the route params.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lng: string }>;
}): Promise<Metadata> {
  const { lng: lngParam } = await params;
  return buildAppMetadata(validateLanguage(lngParam));
}

/**
 * Viewport contract.
 *
 * `viewportFit` is deliberately LEFT AT ITS DEFAULT (`auto`). Under `auto`, iOS
 * confines the viewport to the safe area on notched devices — including in the
 * installed PWA — so no control can end up beneath the home indicator, and
 * `env(safe-area-inset-*)` correctly resolves to 0.
 *
 * Switching to `cover` would extend the page under the system areas and only
 * then require `env(safe-area-inset-*)` padding on every edge-anchored surface
 * (the sticky header, the chat composer, the dialogs). That is an aesthetic
 * change — it buys screen real estate — with a real regression surface, and it
 * cannot be verified without a physical notched device. Not taken.
 *
 * Height sizing uses the DYNAMIC viewport instead (`dvh`, see the
 * `viewport-units` guard): that is what actually moves under the user, as the
 * browser's URL bar retracts and reappears.
 */
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#2563eb',
};

interface LayoutProps {
  children: ReactNode;
  params: Promise<{ lng: string }>;
}

/**
 * Language Layout Component
 *
 * This layout:
 * 1. Loads translations for the current language
 * 2. Provides i18n context to all child components
 * 3. Sets up all application providers (Auth, Query, Theme, etc.)
 */
export default async function LanguageLayout({ children, params }: LayoutProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);

  // The props of a client component are serialised into EVERY page, so the
  // catalogue goes without the subtrees only some routes read; those routes
  // add them back (`i18n/scoped-translations.ts`).
  const resources = {
    [lng]: { [defaultNS]: omitTranslations(translationBundle(lng), ROUTE_SCOPED_TRANSLATIONS) },
  };

  return (
    <html lang={lng} className={`${inter.variable} ${fontVariables}`} suppressHydrationWarning>
      <head>
        {/* Applies data-oled / data-theme before the first paint. Must stay
            FIRST in <head>: everything below it can trigger a paint. */}
        <ThemeInitScript />
        {/* SEO: Structured data (JSON-LD) */}
        <WebSiteJsonLd />
        <OrganizationJsonLd />
      </head>
      <body className="antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <ColorThemeProvider>
            <FontProvider>
              <SnowfallEffect />
              <TranslationsProvider locale={lng} namespaces={['translation']} resources={resources}>
                <ApplicationLocaleSync locale={lng} />
                <QueryProvider>
                  <AuthProvider>
                    <ThemeModeProvider>
                      <IconStyleProvider>
                        <LoggingProvider>
                          <TooltipProvider delayDuration={300}>
                            <ServiceWorkerRegistration />
                            <TelemetryBootstrap />
                            <PresencePing />
                            <FontPreferencesSync />
                            <ColorPreferencesSync />
                            {/* The landing video's one element for the whole
                            visit (ADR-330, amended): framed on the landing,
                            docked on the other public pages, gone on sign-in
                            and in the dashboard. */}
                            <SelectionAssistProvider lng={lng}>
                              <LandingVideoHostSection lng={lng}>
                                {children}
                              </LandingVideoHostSection>
                            </SelectionAssistProvider>
                            <Toaster />
                          </TooltipProvider>
                        </LoggingProvider>
                      </IconStyleProvider>
                    </ThemeModeProvider>
                  </AuthProvider>
                </QueryProvider>
              </TranslationsProvider>
            </FontProvider>
          </ColorThemeProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

/**
 * Generate static params for all supported languages
 * This enables Next.js to pre-render pages for each language
 */
export function generateStaticParams() {
  return languages.map(lng => ({ lng }));
}

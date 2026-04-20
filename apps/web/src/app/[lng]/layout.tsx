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
import { QueryProvider } from '@/lib/query-client';
import { LoggingProvider } from '@/lib/logging-context';
import { ThemeProvider } from '@/components/theme-provider';
import { ColorThemeProvider } from '@/lib/theme-context';
import { FontProvider } from '@/lib/font-context';
import { TranslationsProvider } from '@/components/TranslationsProvider';
import { fontVariables } from '@/lib/fonts';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { SnowfallEffect } from '@/components/effects/SnowfallEffect';
import { languages } from '@/i18n/settings';
import { initI18next, validateLanguage } from '@/i18n';
import { WebSiteJsonLd, OrganizationJsonLd } from '@/components/seo/JsonLd';
import '@/styles/globals.css';
import 'katex/dist/katex.min.css';

// Use local Inter font to avoid network dependency during Docker build
const inter = localFont({
  src: '../../../public/fonts/Inter-Variable.woff2',
  variable: '--font-inter',
  display: 'swap',
  weight: '100 900',
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com'),
  title: 'LIA - Votre assistant personnel',
  description: "Votre assistant personnel intelligent pour la productivité et l'assistance",
  icons: {
    icon: [{ url: '/icon.svg', type: 'image/svg+xml' }],
    apple: [{ url: '/icon.svg', type: 'image/svg+xml' }],
  },
  manifest: '/manifest.json',
  openGraph: {
    type: 'website',
    siteName: 'LIA',
    images: [
      {
        url: '/Title.png',
        width: 2125,
        height: 1193,
        alt: 'LIA — Assistant IA personnel intelligent',
        type: 'image/png',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    images: ['/Title.png'],
  },
};

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

  // Load translations server-side
  const i18n = await initI18next(lng);
  const resources = i18n.options.resources;

  // Debug: Log resources (removed - use logger if needed)

  return (
    <html lang={lng} className={`${inter.variable} ${fontVariables}`} suppressHydrationWarning>
      <head>
        {/* SEO: Structured data (JSON-LD) */}
        <WebSiteJsonLd />
        <OrganizationJsonLd />
        {/* Material Symbols - Google's modern icon font (intentionally loaded via link for icon font) */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
          crossOrigin="anonymous"
        />
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
              <TranslationsProvider
                locale={lng}
                namespaces={['translation']}
                resources={resources || {}}
              >
                <QueryProvider>
                  <AuthProvider>
                    <LoggingProvider>
                      <TooltipProvider delayDuration={300}>
                        {children}
                        <Toaster />
                      </TooltipProvider>
                    </LoggingProvider>
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

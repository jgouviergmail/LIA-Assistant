'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingIllustration, type IllustrationType } from './OnboardingIllustration';

interface OnboardingPageLayoutProps {
  /** Illustration type to display */
  illustration: IllustrationType;
  /** i18n key for page title */
  titleKey: string;
  /** i18n key for page subtitle (optional) */
  subtitleKey?: string;
  /** Current language */
  lng: Language;
  /** Page content */
  children: React.ReactNode;
}

/**
 * Reusable layout for onboarding pages 1-5.
 *
 * Provides consistent structure:
 * - Centered illustration
 * - Title and optional subtitle
 * - Content area for page-specific elements
 */
export function OnboardingPageLayout({
  illustration,
  titleKey,
  subtitleKey,
  lng,
  children,
}: OnboardingPageLayoutProps) {
  const { t } = useTranslation(lng);

  return (
    <div className="flex flex-col items-center space-y-6 sm:space-y-8">
      {/* Illustration */}
      <OnboardingIllustration type={illustration} />

      {/* Title & Subtitle */}
      <div className="text-center space-y-2 sm:space-y-3">
        <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-foreground">
          {t(titleKey)}
        </h1>
        {subtitleKey && (
          <p className="text-base sm:text-lg text-muted-foreground max-w-2xl px-4">
            {t(subtitleKey)}
          </p>
        )}
      </div>

      {/* Page Content */}
      <div className="w-full max-w-2xl px-2 sm:px-4">
        {children}
      </div>
    </div>
  );
}

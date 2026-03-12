'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';

interface Page3PersonalityProps {
  lng: Language;
}

/** Personality example keys matching the i18n structure */
const PERSONALITY_EXAMPLES = ['cynique', 'professeur', 'philosophe', 'adolescent'] as const;

/**
 * Page 3 - Personality
 *
 * Explains the importance of choosing a personality for LIA.
 * Shows example personalities with emoji.
 */
export function Page3Personality({ lng }: Page3PersonalityProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="personality"
      titleKey="onboarding.page3.title"
      subtitleKey="onboarding.page3.subtitle"
      lng={lng}
    >
      {/* Main description */}
      <div className="space-y-4 text-center">
        <p className="text-sm sm:text-base text-muted-foreground">
          {t('onboarding.page3.description')}
        </p>

        {/* Personality examples */}
        <div className="space-y-2 text-left max-w-md md:max-w-2xl lg:max-w-3xl mx-auto">
          {PERSONALITY_EXAMPLES.map((key) => (
            <div
              key={key}
              className="px-4 py-2 rounded-lg bg-muted/50 text-sm"
            >
              {t(`onboarding.page3.examples.${key}`)}
            </div>
          ))}
        </div>

        <p className="text-sm font-medium text-primary">
          {t('onboarding.page3.note')}
        </p>
      </div>
    </OnboardingPageLayout>
  );
}

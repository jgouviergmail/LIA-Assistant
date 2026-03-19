'use client';

import { useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { type Language } from '@/i18n/settings';
import { FAQContent } from './FAQContent';
import { OnboardingTutorial } from '@/components/onboarding';

interface FAQPageClientProps {
  lng: Language;
}

/**
 * Client wrapper for FAQ page that handles onboarding tutorial display.
 * Shows "Show welcome" button if user has completed onboarding.
 */
export function FAQPageClient({ lng }: FAQPageClientProps) {
  const { user } = useAuth();
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Only show the welcome button if user has completed onboarding
  const showWelcomeButton = user?.onboarding_completed === true;

  const handleShowWelcome = () => {
    setShowOnboarding(true);
  };

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
  };

  return (
    <>
      <FAQContent
        lng={lng}
        onShowWelcome={handleShowWelcome}
        showWelcomeButton={showWelcomeButton}
      />

      {/* Onboarding Tutorial Modal */}
      {showOnboarding && (
        <OnboardingTutorial lng={lng} open={showOnboarding} onComplete={handleOnboardingComplete} />
      )}
    </>
  );
}

'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Smartphone } from 'lucide-react';

interface Page6NotificationsProps {
  lng: Language;
}

/**
 * Page 6 - Push Notifications
 *
 * Explains the importance of enabling notifications for reminders.
 */
export function Page6Notifications({ lng }: Page6NotificationsProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="notifications"
      titleKey="onboarding.page6.title"
      subtitleKey="onboarding.page6.subtitle"
      lng={lng}
    >
      {/* Main description */}
      <div className="space-y-4 text-center">
        <p className="text-sm sm:text-base text-muted-foreground">
          {t('onboarding.page6.description')}
        </p>

        {/* Mobile tip */}
        <div className="flex items-center justify-center gap-2 text-xs sm:text-sm text-muted-foreground">
          <Smartphone className="w-4 h-4" />
          <span>{t('onboarding.page6.mobile_tip')}</span>
        </div>
      </div>
    </OnboardingPageLayout>
  );
}

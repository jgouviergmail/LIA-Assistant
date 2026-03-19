'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Card, CardContent } from '@/components/ui/card';
import { Link2, MessageCircleHeart, Brain, Bell, HelpCircle } from 'lucide-react';

interface Page1WelcomeProps {
  lng: Language;
}

const actionItems = [
  {
    icon: Link2,
    titleKey: 'onboarding.page1.actions.connectors',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-500/10',
  },
  {
    icon: MessageCircleHeart,
    titleKey: 'onboarding.page1.actions.personality',
    color: 'text-pink-600 dark:text-pink-400',
    bgColor: 'bg-pink-500/10',
  },
  {
    icon: Brain,
    titleKey: 'onboarding.page1.actions.memory',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-500/10',
  },
  {
    icon: Bell,
    titleKey: 'onboarding.page1.actions.notifications',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-500/10',
  },
];

/**
 * Page 1 - Welcome
 *
 * Introduces LIA and lists the 4 key setup actions.
 */
export function Page1Welcome({ lng }: Page1WelcomeProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="welcome"
      titleKey="onboarding.page1.title"
      subtitleKey="onboarding.page1.subtitle"
      lng={lng}
    >
      {/* Description */}
      <p className="text-center text-sm sm:text-base text-muted-foreground mb-6">
        {t('onboarding.page1.description')}
      </p>

      {/* Action Cards Grid */}
      <div className="grid gap-3 grid-cols-1 md:grid-cols-2">
        {actionItems.map(item => (
          <Card key={item.titleKey} className="border-border/50 bg-card/50">
            <CardContent className="p-4 flex items-center gap-3">
              <div className={`p-2 rounded-lg ${item.bgColor}`}>
                <item.icon className={`w-5 h-5 ${item.color}`} />
              </div>
              <span className="text-sm font-medium">{t(item.titleKey)}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Footer note */}
      <p className="text-center text-xs sm:text-sm text-muted-foreground mt-6">
        {t('onboarding.page1.footer')}
      </p>

      {/* FAQ highlight - more visible */}
      <div className="flex items-center justify-center gap-2 mt-4 p-3 rounded-lg bg-primary/5 border border-primary/20">
        <HelpCircle className="w-5 h-5 text-primary" />
        <span className="text-sm font-medium text-primary">
          {t('onboarding.page1.faq_highlight')}
        </span>
      </div>
    </OnboardingPageLayout>
  );
}

'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Card, CardContent } from '@/components/ui/card';
import { Sparkles, Music, Film, Utensils, Plane, Lightbulb, TrendingUp } from 'lucide-react';

interface Page5InterestsProps {
  lng: Language;
}

const interestExamples = [
  {
    icon: Music,
    titleKey: 'onboarding.page5.examples.music',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-500/10',
  },
  {
    icon: Film,
    titleKey: 'onboarding.page5.examples.cinema',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-500/10',
  },
  {
    icon: Utensils,
    titleKey: 'onboarding.page5.examples.cuisine',
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-500/10',
  },
  {
    icon: Plane,
    titleKey: 'onboarding.page5.examples.travel',
    color: 'text-sky-600 dark:text-sky-400',
    bgColor: 'bg-sky-500/10',
  },
];

/**
 * Page 5 - Interests (Centers of Interest)
 *
 * Explains how LIA learns user interests for personalized conversations.
 */
export function Page5Interests({ lng }: Page5InterestsProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="interests"
      titleKey="onboarding.page5.title"
      subtitleKey="onboarding.page5.subtitle"
      lng={lng}
    >
      {/* Description */}
      <p className="text-center text-sm sm:text-base text-muted-foreground mb-6">
        {t('onboarding.page5.description')}
      </p>

      {/* Examples Grid */}
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2">
        {interestExamples.map((example) => (
          <Card key={example.titleKey} className="border-border/50 bg-card/50">
            <CardContent className="p-4 flex items-center gap-3">
              <div className={`p-2 rounded-lg ${example.bgColor}`}>
                <example.icon className={`w-5 h-5 ${example.color}`} />
              </div>
              <span className="text-sm">{t(example.titleKey)}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tips */}
      <div className="space-y-3 mt-6">
        <div className="flex items-center justify-center gap-2 text-xs sm:text-sm text-muted-foreground">
          <Sparkles className="w-4 h-4 text-primary" />
          <span>{t('onboarding.page5.tip')}</span>
        </div>
        <div className="flex items-center justify-center gap-2 text-xs sm:text-sm text-muted-foreground">
          <TrendingUp className="w-4 h-4 text-emerald-500" />
          <span>{t('onboarding.page5.learning_tip')}</span>
        </div>
        <div className="flex items-center justify-center gap-2 text-xs sm:text-sm text-muted-foreground">
          <Lightbulb className="w-4 h-4 text-amber-500" />
          <span>{t('onboarding.page5.settings_tip')}</span>
        </div>
      </div>
    </OnboardingPageLayout>
  );
}

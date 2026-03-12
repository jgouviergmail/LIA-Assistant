'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Card, CardContent } from '@/components/ui/card';
import { User, Home, Users, Heart, Sparkles, Pin } from 'lucide-react';

interface Page4MemoryProps {
  lng: Language;
}

const memoryExamples = [
  {
    icon: User,
    titleKey: 'onboarding.page4.examples.identity',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-500/10',
  },
  {
    icon: Home,
    titleKey: 'onboarding.page4.examples.addresses',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-500/10',
  },
  {
    icon: Users,
    titleKey: 'onboarding.page4.examples.relations',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-500/10',
  },
  {
    icon: Heart,
    titleKey: 'onboarding.page4.examples.preferences',
    color: 'text-pink-600 dark:text-pink-400',
    bgColor: 'bg-pink-500/10',
  },
];

/**
 * Page 4 - Long-term Memory
 *
 * Explains what information to share with LIA for personalization.
 */
export function Page4Memory({ lng }: Page4MemoryProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="memory"
      titleKey="onboarding.page4.title"
      subtitleKey="onboarding.page4.subtitle"
      lng={lng}
    >
      {/* Description */}
      <p className="text-center text-sm sm:text-base text-muted-foreground mb-6">
        {t('onboarding.page4.description')}
      </p>

      {/* Examples Grid */}
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2">
        {memoryExamples.map((example) => (
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
          <span>{t('onboarding.page4.tip')}</span>
        </div>
        <div className="flex items-center justify-center gap-2 text-xs sm:text-sm text-muted-foreground">
          <Pin className="w-4 h-4 text-amber-500" />
          <span>{t('onboarding.page4.pin_tip')}</span>
        </div>
      </div>
    </OnboardingPageLayout>
  );
}

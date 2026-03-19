'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Card, CardContent } from '@/components/ui/card';
import { Calendar, MapPin, CheckSquare, AlertTriangle } from 'lucide-react';

interface Page2ConnectorsProps {
  lng: Language;
}

const connectorOptions = [
  {
    icon: Calendar,
    titleKey: 'onboarding.page2.options.calendar',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-500/10',
  },
  {
    icon: MapPin,
    titleKey: 'onboarding.page2.options.places',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-500/10',
  },
  {
    icon: CheckSquare,
    titleKey: 'onboarding.page2.options.tasks',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-500/10',
  },
];

/**
 * Page 2 - Connectors
 *
 * Explains the importance of connectors and their customization options.
 */
export function Page2Connectors({ lng }: Page2ConnectorsProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="connectors"
      titleKey="onboarding.page2.title"
      subtitleKey="onboarding.page2.subtitle"
      lng={lng}
    >
      {/* Warning box */}
      <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-500/10 border border-amber-500/20 mb-6">
        <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <p className="text-sm text-muted-foreground">{t('onboarding.page2.warning')}</p>
      </div>

      {/* Description */}
      <p className="text-center text-sm sm:text-base text-muted-foreground mb-6">
        {t('onboarding.page2.description')}
      </p>

      {/* Connector Options */}
      <div className="space-y-3">
        {connectorOptions.map(option => (
          <Card key={option.titleKey} className="border-border/50 bg-card/50">
            <CardContent className="p-4 flex items-center gap-3">
              <div className={`p-2 rounded-lg ${option.bgColor}`}>
                <option.icon className={`w-5 h-5 ${option.color}`} />
              </div>
              <span className="text-sm">{t(option.titleKey)}</span>
            </CardContent>
          </Card>
        ))}
      </div>
    </OnboardingPageLayout>
  );
}

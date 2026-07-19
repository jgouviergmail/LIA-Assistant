'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Search, BookOpen, MapPin, Cloud, Globe, Info, Plug } from 'lucide-react';

interface Page2ConnectorsProps {
  lng: Language;
  /**
   * Volet B (actionable pages): completes the onboarding then navigates to
   * the target — the dialog re-mounts on any navigation while incomplete,
   * so plain links are not an option here.
   */
  onAction?: (href: string) => void;
  isLoading?: boolean;
}

const externalConnectors = [
  {
    icon: Search,
    nameKey: 'onboarding.page2.options.brave_name',
    descKey: 'onboarding.page2.options.brave_desc',
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-500/10',
  },
  {
    icon: BookOpen,
    nameKey: 'onboarding.page2.options.wikipedia_name',
    descKey: 'onboarding.page2.options.wikipedia_desc',
    color: 'text-slate-600 dark:text-slate-400',
    bgColor: 'bg-slate-500/10',
  },
  {
    icon: MapPin,
    nameKey: 'onboarding.page2.options.places_name',
    descKey: 'onboarding.page2.options.places_desc',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-500/10',
  },
  {
    icon: Cloud,
    nameKey: 'onboarding.page2.options.weather_name',
    descKey: 'onboarding.page2.options.weather_desc',
    color: 'text-sky-600 dark:text-sky-400',
    bgColor: 'bg-sky-500/10',
  },
  {
    icon: Globe,
    nameKey: 'onboarding.page2.options.browser_name',
    descKey: 'onboarding.page2.options.browser_desc',
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-500/10',
  },
];

/**
 * Page 2 - Connectors
 *
 * Explains the importance of connectors and their customization options.
 */
export function Page2Connectors({ lng, onAction, isLoading }: Page2ConnectorsProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="connectors"
      titleKey="onboarding.page2.title"
      subtitleKey="onboarding.page2.subtitle"
      lng={lng}
    >
      {/* Provider description */}
      <p className="text-center text-sm sm:text-base text-muted-foreground mb-4">
        {t('onboarding.page2.description')}
      </p>

      {/* Provider note */}
      <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-500/5 border border-blue-500/15 mb-6">
        <Info className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
        <p className="text-xs sm:text-sm text-muted-foreground">
          {t('onboarding.page2.provider_note')}
        </p>
      </div>

      {/* External connectors title */}
      <p className="text-center text-sm sm:text-base text-muted-foreground mb-4">
        {t('onboarding.page2.external_title')}
      </p>

      {/* External Connector Options */}
      <div className="space-y-3">
        {externalConnectors.map(option => (
          <Card key={option.nameKey} className="border-border/50 bg-card/50">
            <CardContent className="p-4 flex items-center gap-3">
              <div className={`p-2 rounded-lg ${option.bgColor}`}>
                <option.icon className={`w-5 h-5 ${option.color}`} />
              </div>
              <span className="text-sm">
                <strong>{t(option.nameKey)}</strong> {t(option.descKey)}
              </span>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Volet B: direct CTA to the connectors settings (completes onboarding
          first — see OnboardingTutorial.handleActionNavigate). */}
      {onAction && (
        <div className="flex justify-center pt-5">
          <Button
            onClick={() => onAction('/dashboard/settings?section=connectors')}
            disabled={isLoading}
            className="min-h-[44px]"
          >
            <Plug className="w-4 h-4 mr-2" />
            {t('onboarding.page2.cta')}
          </Button>
        </div>
      )}
    </OnboardingPageLayout>
  );
}

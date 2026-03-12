'use client';

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { OnboardingPageLayout } from '../OnboardingPageLayout';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Users,
  Mail,
  Calendar,
  CheckSquare,
  FolderOpen,
  Bell,
  MapPin,
  Navigation,
  Cloud,
  Search,
  BookOpen,
  Layers,
  Rocket,
  ChevronLeft,
} from 'lucide-react';

interface Page7ExamplesProps {
  lng: Language;
  onFinish: () => void;
  onPrevious: () => void;
  isLoading: boolean;
}

/**
 * Category definitions for command examples accordion.
 * Each category has an id (matching i18n keys), icon, and theme color.
 */
const EXAMPLE_CATEGORIES = [
  { id: 'contacts', icon: Users, color: 'text-blue-600 dark:text-blue-400' },
  { id: 'emails', icon: Mail, color: 'text-red-600 dark:text-red-400' },
  { id: 'calendar', icon: Calendar, color: 'text-green-600 dark:text-green-400' },
  { id: 'tasks', icon: CheckSquare, color: 'text-purple-600 dark:text-purple-400' },
  { id: 'files', icon: FolderOpen, color: 'text-amber-600 dark:text-amber-400' },
  { id: 'reminders', icon: Bell, color: 'text-orange-600 dark:text-orange-400' },
  { id: 'places', icon: MapPin, color: 'text-pink-600 dark:text-pink-400' },
  { id: 'routes', icon: Navigation, color: 'text-cyan-600 dark:text-cyan-400' },
  { id: 'weather', icon: Cloud, color: 'text-sky-600 dark:text-sky-400' },
  { id: 'perplexity', icon: Search, color: 'text-indigo-600 dark:text-indigo-400' },
  { id: 'wikipedia', icon: BookOpen, color: 'text-slate-600 dark:text-slate-400' },
  { id: 'multi', icon: Layers, color: 'text-teal-600 dark:text-teal-400' },
] as const;

/** Maximum number of examples to attempt loading per category */
const EXAMPLES_PER_CATEGORY = 8;

/**
 * Page 7 - Command Examples
 *
 * Shows example commands organized in an accordion by category.
 * Uses OnboardingPageLayout for DRY compliance.
 * Has a special "OK on y va !" CTA button and a Previous button.
 */
export function Page7Examples({ lng, onFinish, onPrevious, isLoading }: Page7ExamplesProps) {
  const { t } = useTranslation(lng);

  return (
    <OnboardingPageLayout
      illustration="examples"
      titleKey="onboarding.page7.title"
      subtitleKey="onboarding.page7.subtitle"
      lng={lng}
    >
      {/* Accordion with categories */}
      <Accordion type="single" collapsible className="w-full">
        {EXAMPLE_CATEGORIES.map((category) => {
          const CategoryIcon = category.icon;
          return (
            <AccordionItem key={category.id} value={category.id}>
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-3">
                  <CategoryIcon className={`w-5 h-5 ${category.color}`} />
                  <span className="font-medium">
                    {t(`onboarding.page7.categories.${category.id}.title`)}
                  </span>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <ul className="space-y-2 pl-8">
                  {Array.from({ length: EXAMPLES_PER_CATEGORY }, (_, i) => i + 1).map((i) => {
                    const exampleKey = `onboarding.page7.categories.${category.id}.example${i}`;
                    const example = t(exampleKey);
                    // Only render if translation exists (not returning the key itself)
                    if (example === exampleKey) return null;
                    return (
                      <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                        <span className="text-primary mt-0.5">•</span>
                        <span className="italic">&quot;{example}&quot;</span>
                      </li>
                    );
                  })}
                </ul>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>

      {/* Buttons - Previous left, Finish right */}
      <div className="flex flex-col sm:flex-row justify-center gap-3 pt-4 sm:pt-6">
        <Button
          variant="outline"
          onClick={onPrevious}
          disabled={isLoading}
          className="min-h-[44px] sm:min-h-[48px] order-2 sm:order-1"
        >
          <ChevronLeft className="h-4 w-4 mr-2" />
          <span className="hidden sm:inline">{t('common.previous')}</span>
          <span className="sm:hidden">{t('common.previous_short')}</span>
        </Button>
        <Button
          onClick={onFinish}
          disabled={isLoading}
          size="lg"
          className="min-h-[48px] px-8 text-base font-semibold order-1 sm:order-2"
        >
          {isLoading ? (
            <>
              <LoadingSpinner size="sm" className="mr-2" />
              {t('common.loading')}
            </>
          ) : (
            <>
              <Rocket className="w-5 h-5 mr-2" />
              {t('onboarding.page7.cta')}
            </>
          )}
        </Button>
      </div>
    </OnboardingPageLayout>
  );
}

'use client';

import { useState, useRef, useEffect } from 'react';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { Dialog } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { ChevronLeft, ChevronRight, Sparkles } from 'lucide-react';
import { ONBOARDING_TOTAL_PAGES, ONBOARDING_SCROLL_BEHAVIOR } from '@/lib/constants';
import { OnboardingDialogContent } from './OnboardingDialogContent';
import { Page1Welcome } from './pages/Page1Welcome';
import { Page2Connectors } from './pages/Page2Connectors';
import { Page3Personality } from './pages/Page3Personality';
import { Page4Memory } from './pages/Page4Memory';
import { Page5Interests } from './pages/Page5Interests';
import { Page6Notifications } from './pages/Page6Notifications';
import { Page7Examples } from './pages/Page7Examples';

interface OnboardingTutorialProps {
  lng: Language;
  open: boolean;
  onComplete: () => void;
}

/**
 * Onboarding Tutorial Dialog
 *
 * A 6-page guided tutorial that introduces new users to LIA.
 * - Cannot be closed via X or Escape (must use explicit buttons)
 * - "Ne plus afficher" dismisses permanently
 * - "OK on y va !" on last page completes the tutorial
 */
export function OnboardingTutorial({ lng, open, onComplete }: OnboardingTutorialProps) {
  const { t } = useTranslation(lng);
  const { refreshUser } = useAuth();
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  // Reset scroll position and focus when page changes (accessibility)
  useEffect(() => {
    if (contentRef.current) {
      // Scroll to top
      contentRef.current.scrollTo({ top: 0, behavior: ONBOARDING_SCROLL_BEHAVIOR });

      // Focus on the page heading for screen readers
      const heading = contentRef.current.querySelector('h1');
      if (heading instanceof HTMLElement) {
        heading.setAttribute('tabindex', '-1');
        heading.focus({ preventScroll: true });
      }
    }
  }, [currentPage]);

  // Mark onboarding as completed in the backend
  const handleDismiss = async () => {
    if (isLoading) return;
    setIsLoading(true);

    try {
      await apiClient.patch('/auth/me/onboarding-preference', {
        onboarding_completed: true,
      });

      // Close dialog immediately after successful PATCH
      onComplete();

      // Refresh user in background (non-blocking)
      refreshUser().catch(error => {
        console.error('Failed to refresh user after onboarding:', error);
      });
    } catch (error) {
      console.error('Failed to update onboarding preference:', error);
      toast.error(t('common.error'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleNext = () => {
    if (currentPage < ONBOARDING_TOTAL_PAGES) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const handlePrevious = () => {
    if (currentPage > 1) {
      setCurrentPage(prev => prev - 1);
    }
  };

  const handleFinish = () => {
    // Just close the dialog - onboarding_completed stays false
    // User can see the tutorial again next time
    onComplete();
  };

  const renderPage = () => {
    switch (currentPage) {
      case 1:
        return <Page1Welcome lng={lng} />;
      case 2:
        return <Page2Connectors lng={lng} />;
      case 3:
        return <Page3Personality lng={lng} />;
      case 4:
        return <Page4Memory lng={lng} />;
      case 5:
        return <Page5Interests lng={lng} />;
      case 6:
        return <Page6Notifications lng={lng} />;
      case 7:
        return (
          <Page7Examples
            lng={lng}
            onFinish={handleFinish}
            onPrevious={handlePrevious}
            isLoading={isLoading}
          />
        );
      default:
        return null;
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <OnboardingDialogContent
        lng={lng}
        onEscapeKeyDown={e => e.preventDefault()}
        onInteractOutside={e => e.preventDefault()}
      >
        {/* Header - sticky */}
        <div className="sticky top-0 z-10 flex flex-col sm:flex-row sm:items-center sm:justify-between px-4 sm:px-6 py-3 sm:py-4 gap-2 sm:gap-0 border-b bg-background">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <Sparkles className="h-4 w-4 text-primary" />
            </div>
            <span className="font-semibold text-foreground">LIA</span>
          </div>
          <span className="text-sm text-muted-foreground" aria-live="polite">
            {t('onboarding.page_indicator', {
              current: currentPage,
              total: ONBOARDING_TOTAL_PAGES,
            })}
          </span>
        </div>

        {/* Content - scrollable */}
        <div ref={contentRef} className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
          {renderPage()}
        </div>

        {/* Footer - sticky (hidden on page 7 which has its own CTA) */}
        {currentPage < ONBOARDING_TOTAL_PAGES && (
          <div className="sticky bottom-0 z-10 flex items-center justify-between gap-2 px-4 sm:px-6 py-4 border-t bg-background">
            {/* Previous button - left side */}
            <div className="flex-1 flex justify-start">
              {currentPage > 1 && (
                <Button
                  variant="outline"
                  onClick={handlePrevious}
                  disabled={isLoading}
                  className="min-h-[44px]"
                >
                  <ChevronLeft className="h-4 w-4 mr-1 sm:mr-2" />
                  <span className="hidden sm:inline">{t('common.previous')}</span>
                  <span className="sm:hidden">{t('common.previous_short')}</span>
                </Button>
              )}
            </div>

            {/* Skip button - center */}
            <Button
              variant="ghost"
              onClick={handleDismiss}
              disabled={isLoading}
              className="min-h-[44px] text-muted-foreground"
            >
              {isLoading && <LoadingSpinner size="sm" className="mr-2" />}
              {t('onboarding.skip')}
            </Button>

            {/* Next button - right side */}
            <div className="flex-1 flex justify-end">
              <Button onClick={handleNext} disabled={isLoading} className="min-h-[44px]">
                <span className="hidden sm:inline">{t('common.next')}</span>
                <span className="sm:hidden">{t('common.next_short')}</span>
                <ChevronRight className="h-4 w-4 ml-1 sm:ml-2" />
              </Button>
            </div>
          </div>
        )}
      </OnboardingDialogContent>
    </Dialog>
  );
}

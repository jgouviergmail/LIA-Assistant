'use client';

import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { DialogPortal, DialogOverlay, DialogTitle, DialogDescription } from '@/components/ui/dialog';

interface OnboardingDialogContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  /** Current language for accessibility translations */
  lng: Language;
}

/**
 * Custom DialogContent for onboarding tutorial.
 *
 * Differences from standard DialogContent:
 * - No X button (users must use explicit "Skip" or "Finish" buttons)
 * - Full-height on mobile, constrained on desktop
 * - Flex layout for header/content/footer structure
 * - Includes visually hidden DialogTitle/Description for accessibility (i18n)
 */
export const OnboardingDialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  OnboardingDialogContentProps
>(({ className, children, lng, ...props }, ref) => {
  const { t } = useTranslation(lng);

  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          // Base positioning
          'fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%]',
          // Responsive sizing
          'w-[95vw] sm:w-[90vw] md:max-w-2xl lg:max-w-4xl',
          'h-[92vh] sm:h-[88vh] md:h-[85vh]',
          // Layout - flex column for header/content/footer
          'flex flex-col overflow-hidden',
          // Style
          'border bg-background shadow-lg',
          'rounded-none sm:rounded-lg',
          // Animation
          'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
          className
        )}
        {...props}
      >
        {/* Visually hidden title/description for screen readers (accessibility) */}
        <DialogTitle className="sr-only">{t('onboarding.dialog_title')}</DialogTitle>
        <DialogDescription className="sr-only">
          {t('onboarding.dialog_description')}
        </DialogDescription>
        {children}
        {/* No DialogPrimitive.Close here - users must use explicit buttons */}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
});
OnboardingDialogContent.displayName = 'OnboardingDialogContent';

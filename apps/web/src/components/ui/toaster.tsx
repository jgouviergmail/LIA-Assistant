'use client';

import { useTheme } from 'next-themes';
import { Toaster as Sonner } from 'sonner';
import { useTranslation } from 'react-i18next';

type ToasterProps = React.ComponentProps<typeof Sonner>;

/** Shared glass material; Sonner retains timers, stacking, swipe and live announcements. */
const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = 'system' } = useTheme();
  const { t } = useTranslation();

  return (
    <Sonner
      theme={theme as ToasterProps['theme']}
      className="toaster group"
      position="top-center"
      expand={true}
      visibleToasts={4}
      gap={16}
      offset={32}
      duration={5000}
      closeButton={true}
      toastOptions={{
        // Native Sonner paint is unlayered and overrides Tailwind's layers.
        // Its supported unstyled boundary leaves behaviour with the library.
        unstyled: true,
        closeButtonAriaLabel: t('common.close'),
        classNames: {
          toast: 'lia-overlay-surface lia-notification rounded-2xl border text-foreground',
          content: 'min-w-0 flex-1',
          icon: 'lia-notification-icon',
          title: 'text-sm font-semibold leading-relaxed',
          description: 'mt-1 text-sm leading-relaxed text-foreground/80',
          actionButton:
            'inline-flex min-h-11 items-center justify-center rounded-xl bg-primary px-3 text-sm font-semibold text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
          cancelButton:
            'inline-flex min-h-11 items-center justify-center rounded-xl bg-muted px-3 text-sm font-medium text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
          closeButton:
            'lia-notification-close inline-flex h-11 w-11 items-center justify-center rounded-xl text-foreground/80 hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        },
      }}
      {...props}
    />
  );
};

export { Toaster };

import { type ReactNode, useEffect, useState } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export type AlertVariant = 'success' | 'error' | 'warning' | 'info';

export interface AlertProps {
  variant: AlertVariant;
  children: ReactNode;
  dismissible?: boolean;
  onDismiss?: () => void;
  autoDismiss?: number; // milliseconds
  className?: string;
}

/**
 * Alert component with accessibility support (WCAG AA compliant)
 *
 * Features:
 * - ARIA live regions for screen readers
 * - Keyboard navigation (Escape to dismiss)
 * - Auto-dismiss with configurable timeout
 * - Multiple variants with appropriate colors and icons
 * - Compound component pattern for flexibility
 *
 * @example
 * <Alert variant="success" dismissible onDismiss={() => {}}>
 *   <Alert.Icon />
 *   <Alert.Content>Operation completed successfully!</Alert.Content>
 * </Alert>
 */
export function Alert({
  variant,
  children,
  dismissible = false,
  onDismiss,
  autoDismiss,
  className,
}: AlertProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    if (autoDismiss && autoDismiss > 0) {
      const timer = setTimeout(() => {
        setIsVisible(false);
        onDismiss?.();
      }, autoDismiss);

      return () => clearTimeout(timer);
    }
  }, [autoDismiss, onDismiss]);

  useEffect(() => {
    if (!dismissible) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsVisible(false);
        onDismiss?.();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [dismissible, onDismiss]);

  if (!isVisible) return null;

  const variantStyles = {
    success: 'bg-success/10 border-success/30 text-success shadow-sm',
    error: 'bg-destructive/10 border-destructive/30 text-destructive shadow-sm',
    warning: 'bg-warning/10 border-warning/30 text-warning-foreground shadow-sm',
    info: 'bg-primary/10 border-primary/30 text-primary shadow-sm',
  };

  return (
    <div
      role="alert"
      aria-live="polite"
      aria-atomic="true"
      className={cn(
        'rounded-lg border-2 p-4 backdrop-blur-sm transition-all duration-200 animate-in fade-in-50 slide-in-from-top-2',
        variantStyles[variant],
        className
      )}
    >
      <div className="flex">
        {children}
        {dismissible && (
          <div className="ml-auto pl-3">
            <button
              type="button"
              onClick={() => {
                setIsVisible(false);
                onDismiss?.();
              }}
              className={cn(
                'inline-flex rounded-md p-1.5 transition-all duration-200 hover:scale-110',
                variant === 'success' && 'text-success hover:bg-success/20',
                variant === 'error' && 'text-destructive hover:bg-destructive/20',
                variant === 'warning' && 'text-warning-foreground hover:bg-warning/20',
                variant === 'info' && 'text-primary hover:bg-primary/20'
              )}
              aria-label="Dismiss notification"
            >
              <span className="sr-only">Dismiss</span>
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Alert.Icon - Display appropriate icon based on variant with Lucide icons
 */
Alert.Icon = function AlertIcon({ variant }: { variant: AlertVariant }) {
  const iconMap = {
    success: CheckCircle2,
    error: XCircle,
    warning: AlertTriangle,
    info: Info,
  };

  const IconComponent = iconMap[variant];

  return (
    <div className="flex-shrink-0">
      <IconComponent className="h-5 w-5" aria-hidden="true" />
    </div>
  );
};

/**
 * Alert.Content - Wrapper for alert message content
 */
Alert.Content = function AlertContent({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn('ml-3', className)}>{children}</div>;
};

/**
 * Alert.Title - Optional title for alert
 */
Alert.Title = function AlertTitle({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <h3 className={cn('text-sm font-medium', className)}>{children}</h3>;
};

/**
 * Alert.Description - Alert message text
 */
Alert.Description = function AlertDescription({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <p className={cn('text-sm font-medium', className)}>{children}</p>;
};

// Named exports for convenience
export const AlertTitle = Alert.Title;
export const AlertDescription = Alert.Description;
export const AlertIcon = Alert.Icon;
export const AlertContent = Alert.Content;

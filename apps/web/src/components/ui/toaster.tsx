'use client';

import { useTheme } from 'next-themes';
import { Toaster as Sonner } from 'sonner';

type ToasterProps = React.ComponentProps<typeof Sonner>;

/**
 * Toaster component with premium notification styling.
 *
 * Enhanced design:
 * - Larger size with glassmorphism effect
 * - Elegant shadows and borders
 * - Smooth animations
 * - Better color contrast
 *
 * Configuration:
 * - Position: Top center (horizontal middle, 32px from top)
 * - Stacking: Vertical expansion without overlap
 * - Duration: 5s default
 * - Max visible: 4 toasts at once
 * - Color coding with premium accents
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = 'system' } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps['theme']}
      className="toaster group"
      // Position: top center
      position="top-center"
      // Visual configuration
      expand={true} // Expand on hover to show all toasts
      visibleToasts={4} // Max 4 toasts visible at once
      gap={16} // 16px gap between toasts
      offset={32} // 32px from top edge
      // Timing
      duration={5000} // 5s default duration (longer for better readability)
      closeButton={true} // Show close button
      richColors={true} // Enable color-coded toasts
      toastOptions={{
        classNames: {
          // Base toast styling - Larger, with glassmorphism and premium shadows
          toast: `
            group toast
            group-[.toaster]:bg-card/95
            group-[.toaster]:backdrop-blur-md
            group-[.toaster]:text-foreground
            group-[.toaster]:border-2
            group-[.toaster]:border-border/60
            group-[.toaster]:shadow-xl
            group-[.toaster]:rounded-xl
            group-[.toaster]:px-5
            group-[.toaster]:py-4
            group-[.toaster]:min-w-[320px]
            group-[.toaster]:max-w-[420px]
          `,
          // Title text - Larger and bolder
          title: 'group-[.toast]:text-base group-[.toast]:font-semibold',
          // Description text - Better size and spacing
          description:
            'group-[.toast]:text-muted-foreground group-[.toast]:text-sm group-[.toast]:mt-1.5 group-[.toast]:leading-relaxed',
          // Action button - More prominent
          actionButton: `
            group-[.toast]:bg-primary
            group-[.toast]:text-primary-foreground
            group-[.toast]:px-4
            group-[.toast]:py-2
            group-[.toast]:rounded-lg
            group-[.toast]:text-sm
            group-[.toast]:font-semibold
            group-[.toast]:shadow-md
            group-[.toast]:hover:opacity-90
            group-[.toast]:transition-opacity
          `,
          // Cancel button
          cancelButton: `
            group-[.toast]:bg-muted
            group-[.toast]:text-muted-foreground
            group-[.toast]:px-4
            group-[.toast]:py-2
            group-[.toast]:rounded-lg
            group-[.toast]:text-sm
            group-[.toast]:font-medium
          `,
          // Close button - Styled elegantly
          closeButton: `
            group-[.toast]:bg-card/80
            group-[.toast]:text-muted-foreground
            group-[.toast]:border
            group-[.toast]:border-border/50
            group-[.toast]:rounded-full
            group-[.toast]:hover:bg-muted
            group-[.toast]:hover:text-foreground
            group-[.toast]:transition-colors
          `,
          // Success toast - Premium green
          success: `
            group-[.toaster]:border-success/40
            group-[.toaster]:bg-success/10
            dark:group-[.toaster]:bg-success/15
            group-[.toaster]:text-success
            dark:group-[.toaster]:text-success
            group-[.toaster]:shadow-success/10
          `,
          // Error toast - Premium red
          error: `
            group-[.toaster]:border-destructive/40
            group-[.toaster]:bg-destructive/10
            dark:group-[.toaster]:bg-destructive/15
            group-[.toaster]:text-destructive
            dark:group-[.toaster]:text-destructive
            group-[.toaster]:shadow-destructive/10
          `,
          // Info toast - Premium blue
          info: `
            group-[.toaster]:border-primary/40
            group-[.toaster]:bg-primary/10
            dark:group-[.toaster]:bg-primary/15
            group-[.toaster]:text-primary
            dark:group-[.toaster]:text-primary
            group-[.toaster]:shadow-primary/10
          `,
          // Warning toast - Premium orange
          warning: `
            group-[.toaster]:border-warning/40
            group-[.toaster]:bg-warning/10
            dark:group-[.toaster]:bg-warning/15
            group-[.toaster]:text-warning-foreground
            dark:group-[.toaster]:text-warning
            group-[.toaster]:shadow-warning/10
          `,
        },
      }}
      {...props}
    />
  );
};

export { Toaster };

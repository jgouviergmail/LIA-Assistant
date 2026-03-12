'use client';

import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn, proxyGoogleImageUrl } from '@/lib/utils';
import { Skeleton } from './skeleton';

/**
 * Avatar Component - Generic, Reusable Profile Picture/Image Component
 *
 * Features:
 * - Multiple shape variants (circular, rounded, square)
 * - Size variants (xs to 2xl)
 * - Automatic fallback to initials with color-hashed background
 * - Lazy loading with skeleton placeholder
 * - Glassmorphism effects with gradient overlays
 * - Hover effects (glow, scale, shadow)
 * - Accessibility (alt text, ARIA labels)
 * - Status badge support (online, verified, etc.)
 *
 * Architecture:
 * - Uses class-variance-authority for type-safe variants
 * - Follows existing UI component patterns (button.tsx, badge.tsx)
 * - Integrates with Tailwind 4.0 OKLCH color system
 * - Generic and reusable across all domains (contacts, users, messages, etc.)
 *
 * @example
 * ```tsx
 * // Profile photo with circular shape
 * <Avatar
 *   src="https://..."
 *   alt="John Doe"
 *   name="John Doe"
 *   size="lg"
 *   variant="circular"
 * />
 *
 * // Fallback to initials if no src
 * <Avatar name="Jane Smith" size="md" variant="circular" />
 *
 * // With status badge
 * <Avatar
 *   src="https://..."
 *   name="Alice"
 *   status="online"
 *   variant="circular"
 * />
 * ```
 */

// ============================================================================
// UTILITIES
// ============================================================================

/**
 * Generate a deterministic color from a string (name)
 * Uses djb2 hash algorithm for consistent color per name
 */
function stringToColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }

  // Convert hash to HSL with fixed saturation and lightness
  const hue = Math.abs(hash % 360);
  return `hsl(${hue}, 60%, 50%)`; // Vibrant but not too saturated
}

/**
 * Extract initials from a name
 * Handles multi-part names (first + last initial)
 */
function getInitials(name: string): string {
  if (!name) return '?';

  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].charAt(0).toUpperCase();
  }

  // First initial + last initial
  const first = parts[0].charAt(0);
  const last = parts[parts.length - 1].charAt(0);
  return (first + last).toUpperCase();
}

// ============================================================================
// VARIANTS (CVA)
// ============================================================================

const avatarVariants = cva(
  // Base styles (common to all variants)
  'relative inline-flex items-center justify-center overflow-hidden font-semibold select-none transition-all duration-300',
  {
    variants: {
      /**
       * Shape variants
       */
      variant: {
        circular: 'rounded-full',
        rounded: 'rounded-lg',
        square: 'rounded-none',
      },

      /**
       * Size variants
       */
      size: {
        xs: 'h-6 w-6 text-[10px]', // 24px - tiny icons
        sm: 'h-8 w-8 text-xs', // 32px - compact lists
        md: 'h-12 w-12 text-sm', // 48px - default size
        lg: 'h-16 w-16 text-base', // 64px - prominent display
        xl: 'h-24 w-24 text-lg', // 96px - profile headers
        '2xl': 'h-32 w-32 text-xl', // 128px - large profiles
      },

      /**
       * Effect variants (visual enhancements)
       */
      effect: {
        none: '',
        glass: 'border-2 border-border/30 shadow-lg hover:shadow-xl',
        glow: 'shadow-lg hover:shadow-2xl hover:scale-105',
      },
    },
    defaultVariants: {
      variant: 'circular',
      size: 'md',
      effect: 'glass',
    },
  }
);

const overlayVariants = cva('absolute inset-0 pointer-events-none', {
  variants: {
    variant: {
      circular: 'rounded-full',
      rounded: 'rounded-lg',
      square: 'rounded-none',
    },
    effect: {
      none: 'hidden',
      glass: 'bg-gradient-to-br from-transparent via-transparent to-background/10',
      glow: 'bg-gradient-to-br from-transparent via-transparent to-primary/5',
    },
  },
  defaultVariants: {
    variant: 'circular',
    effect: 'glass',
  },
});

// ============================================================================
// STATUS BADGE (Optional addon)
// ============================================================================

interface StatusBadgeProps {
  status: 'online' | 'offline' | 'away' | 'busy' | 'verified';
  size: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';
}

type StatusConfig = {
  color: string;
  label: string;
  icon?: string;
};

const statusConfig: Record<'online' | 'offline' | 'away' | 'busy' | 'verified', StatusConfig> = {
  online: { color: 'bg-success', label: 'Online' },
  offline: { color: 'bg-muted', label: 'Offline' },
  away: { color: 'bg-warning', label: 'Away' },
  busy: { color: 'bg-destructive', label: 'Busy' },
  verified: { color: 'bg-primary', label: 'Verified', icon: '✓' },
};

const badgeSizeMap = {
  xs: 'h-1.5 w-1.5',
  sm: 'h-2 w-2',
  md: 'h-3 w-3',
  lg: 'h-4 w-4',
  xl: 'h-5 w-5',
  '2xl': 'h-6 w-6',
};

function StatusBadge({ status, size }: StatusBadgeProps) {
  const config = statusConfig[status];
  const sizeClass = badgeSizeMap[size];

  return (
    <span
      className={cn(
        'absolute bottom-0 right-0 rounded-full border-2 border-background flex items-center justify-center',
        config.color,
        sizeClass
      )}
      aria-label={config.label}
      title={config.label}
    >
      {config.icon && <span className="text-[8px] text-white font-bold">{config.icon}</span>}
    </span>
  );
}

// ============================================================================
// MAIN AVATAR COMPONENT
// ============================================================================

export interface AvatarProps extends VariantProps<typeof avatarVariants> {
  /** Image source URL */
  src?: string;
  /** Alt text for accessibility (required if src provided) */
  alt?: string;
  /** Display name (used for initials fallback and color generation) */
  name?: string;
  /** Status badge */
  status?: 'online' | 'offline' | 'away' | 'busy' | 'verified';
  /** Additional CSS classes */
  className?: string;
  /** Disable hover effects */
  disableHover?: boolean;
  /** Loading state */
  loading?: boolean;
  /** Click handler */
  onClick?: () => void;
}

export function Avatar({
  src,
  alt,
  name = '',
  status,
  variant = 'circular',
  size = 'md',
  effect = 'glass',
  className,
  disableHover = false,
  loading = false,
  onClick,
}: AvatarProps) {
  const [imageLoaded, setImageLoaded] = React.useState(false);
  const [imageError, setImageError] = React.useState(false);
  const initials = React.useMemo(() => getInitials(name), [name]);
  const bgColor = React.useMemo(() => stringToColor(name || 'Anonymous'), [name]);

  // Show initials if: no src, image error, or loading
  const showInitials = !src || imageError || loading;

  return (
    <div
      className={cn(
        'group relative inline-block',
        onClick && 'cursor-pointer',
        !disableHover && effect === 'glow' && 'hover:scale-105',
        className
      )}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {/* Glow effect background (only for 'glow' effect) */}
      {!disableHover && effect === 'glow' && (
        <div className="absolute inset-0 bg-gradient-radial from-primary/20 via-primary/5 to-transparent rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      )}

      {/* Main avatar container */}
      <div
        className={cn(avatarVariants({ variant, size, effect }), onClick && 'active:scale-95')}
        style={{
          backgroundColor: showInitials ? bgColor : undefined,
        }}
      >
        {/* Loading skeleton */}
        {loading && (
          <Skeleton
            className={cn(
              'absolute inset-0',
              variant === 'circular' ? 'rounded-full' : 'rounded-lg'
            )}
          />
        )}

        {/* Image */}
        {src && !imageError && (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={proxyGoogleImageUrl(src) || src}
              alt={alt || name || 'Avatar'}
              className={cn(
                'h-full w-full object-cover transition-opacity duration-300',
                imageLoaded ? 'opacity-100' : 'opacity-0'
              )}
              loading="lazy"
              onLoad={() => setImageLoaded(true)}
              onError={() => {
                setImageError(true);
                setImageLoaded(false);
              }}
            />

            {/* Gradient overlay for depth */}
            <div className={cn(overlayVariants({ variant, effect }), 'z-10')} />
          </>
        )}

        {/* Initials fallback */}
        {showInitials && !loading && (
          <span className="relative z-20 text-white drop-shadow-sm">{initials}</span>
        )}

        {/* Status badge */}
        {status && size && <StatusBadge status={status} size={size} />}
      </div>
    </div>
  );
}

// ============================================================================
// AVATAR GROUP (for displaying multiple avatars)
// ============================================================================

export interface AvatarGroupProps {
  /** Array of avatar props */
  avatars: AvatarProps[];
  /** Maximum avatars to display before showing "+N" */
  max?: number;
  /** Size of avatars in group */
  size?: AvatarProps['size'];
  /** Spacing between avatars */
  spacing?: 'tight' | 'normal' | 'loose';
  /** Additional CSS classes */
  className?: string;
}

const spacingMap = {
  tight: '-space-x-2',
  normal: '-space-x-4',
  loose: '-space-x-6',
};

export function AvatarGroup({
  avatars,
  max = 5,
  size = 'md',
  spacing = 'normal',
  className,
}: AvatarGroupProps) {
  const displayAvatars = avatars.slice(0, max);
  const remaining = avatars.length - max;

  return (
    <div className={cn('flex items-center', spacingMap[spacing], className)}>
      {displayAvatars.map((avatar, index) => (
        <Avatar key={index} {...avatar} size={size} className="ring-2 ring-background" />
      ))}

      {remaining > 0 && (
        <div
          className={cn(
            avatarVariants({ size, variant: 'circular' }),
            'bg-muted text-muted-foreground ring-2 ring-background'
          )}
        >
          <span className="text-xs font-semibold">+{remaining}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Export utility functions for external use
 */
export { stringToColor, getInitials };

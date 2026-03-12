/**
 * StatusBadge - Status indicator badge component.
 *
 * Provides semantic status visualization for permissions, states, etc.
 * Uses the existing Badge component internally for DRY compliance.
 * Adds status-specific colors and icons on top.
 */

import { CheckCircle2, XCircle, AlertTriangle, Info, HelpCircle } from 'lucide-react';

import { Badge, type BadgeProps } from './badge';
import { cn } from '@/lib/utils';

const statusConfig = {
  granted: {
    variant: 'default' as const,
    className: 'bg-green-500/10 text-green-600 border-green-500/20 dark:bg-green-900/30 dark:text-green-400',
    Icon: CheckCircle2,
  },
  denied: {
    variant: 'destructive' as const,
    className: 'bg-red-500/10 text-red-600 border-red-500/20 dark:bg-red-900/30 dark:text-red-400',
    Icon: XCircle,
  },
  warning: {
    variant: 'default' as const,
    className: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20 dark:bg-yellow-900/30 dark:text-yellow-400',
    Icon: AlertTriangle,
  },
  info: {
    variant: 'default' as const,
    className: 'bg-blue-500/10 text-blue-600 border-blue-500/20 dark:bg-blue-900/30 dark:text-blue-400',
    Icon: Info,
  },
  pending: {
    variant: 'secondary' as const,
    className: '',
    Icon: HelpCircle,
  },
  unknown: {
    variant: 'outline' as const,
    className: '',
    Icon: HelpCircle,
  },
  // Browser permission states
  unsupported: {
    variant: 'secondary' as const,
    className: '',
    Icon: AlertTriangle,
  },
  default: {
    variant: 'outline' as const,
    className: '',
    Icon: AlertTriangle,
  },
} as const;

export type StatusType = keyof typeof statusConfig;

export interface StatusBadgeProps extends Omit<BadgeProps, 'variant' | 'icon'> {
  /** Status type determines color and icon */
  status: StatusType;
  /** Optional custom label (defaults to capitalized status) */
  label?: string;
  /** Show status icon (default: true) */
  showIcon?: boolean;
}

/**
 * Status badge component for displaying permission/state status.
 *
 * Built on top of Badge component for DRY compliance.
 *
 * Usage:
 * ```tsx
 * // Basic usage
 * <StatusBadge status="granted" />
 *
 * // With custom label (i18n)
 * <StatusBadge status="denied" label={t('status.blocked')} />
 *
 * // Without icon
 * <StatusBadge status="warning" showIcon={false} />
 * ```
 */
export function StatusBadge({
  status,
  label,
  showIcon = true,
  className,
  size,
  ...props
}: StatusBadgeProps) {
  const config = statusConfig[status];
  const displayLabel = label ?? status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <Badge
      variant={config.variant}
      size={size}
      icon={showIcon ? <config.Icon className="h-3 w-3" /> : undefined}
      className={cn(config.className, className)}
      {...props}
    >
      {displayLabel}
    </Badge>
  );
}

/**
 * Simple status dot for compact displays.
 */
export interface StatusDotProps {
  status: StatusType;
  className?: string;
  title?: string;
}

const dotColors: Record<StatusType, string> = {
  granted: 'bg-green-500',
  denied: 'bg-red-500',
  warning: 'bg-yellow-500',
  info: 'bg-blue-500',
  pending: 'bg-gray-400',
  unknown: 'bg-gray-400',
  unsupported: 'bg-gray-400',
  default: 'bg-gray-400',
};

export function StatusDot({ status, className, title }: StatusDotProps) {
  return (
    <span
      className={cn('inline-block h-2 w-2 rounded-full', dotColors[status], className)}
      title={title ?? status}
      role="status"
      aria-label={title ?? status}
    />
  );
}

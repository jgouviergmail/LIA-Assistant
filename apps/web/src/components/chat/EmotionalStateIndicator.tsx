'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * Emotional state types matching backend EmotionalState enum.
 */
export type EmotionalState = 'comfort' | 'danger' | 'neutral';

/**
 * Configuration for each emotional state.
 */
const EMOTIONAL_CONFIG: Record<
  EmotionalState,
  {
    color: string;
    bgColor: string;
    borderColor: string;
    icon: string;
    label: string;
    description: string;
  }
> = {
  comfort: {
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/20',
    borderColor: 'border-green-300 dark:border-green-700',
    icon: '🟢',
    label: 'Terrain positif',
    description: 'Souvenirs positifs activés',
  },
  danger: {
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/20',
    borderColor: 'border-red-300 dark:border-red-700',
    icon: '🔴',
    label: 'Zone sensible',
    description: 'Sujet délicat détecté',
  },
  neutral: {
    color: 'text-gray-500 dark:text-gray-400',
    bgColor: 'bg-gray-100 dark:bg-gray-800/30',
    borderColor: 'border-gray-300 dark:border-gray-600',
    icon: '⚪',
    label: 'Mode factuel',
    description: 'Conversation neutre',
  },
};

interface EmotionalStateIndicatorProps {
  /**
   * The emotional state to display.
   */
  state: EmotionalState;
  /**
   * Display variant.
   * - 'icon': Just the emoji icon (minimal)
   * - 'badge': Icon with label
   * - 'full': Icon, label, and description
   */
  variant?: 'icon' | 'badge' | 'full';
  /**
   * Size variant.
   */
  size?: 'sm' | 'md' | 'lg';
  /**
   * Additional CSS classes.
   */
  className?: string;
  /**
   * Show tooltip on hover.
   */
  showTooltip?: boolean;
}

/**
 * Visual indicator for the emotional state during conversations.
 *
 * Shows subtle feedback when memories are injected:
 * - Comfort (green): Positive memories dominant
 * - Danger (red): Sensitive topics detected
 * - Neutral (gray): Factual mode, no emotional context
 *
 * @example
 * ```tsx
 * // Minimal icon
 * <EmotionalStateIndicator state="comfort" variant="icon" />
 *
 * // Badge with label
 * <EmotionalStateIndicator state="danger" variant="badge" />
 *
 * // Full display
 * <EmotionalStateIndicator state="neutral" variant="full" />
 * ```
 */
export function EmotionalStateIndicator({
  state,
  variant = 'icon',
  size = 'md',
  className,
  showTooltip = true,
}: EmotionalStateIndicatorProps) {
  const config = EMOTIONAL_CONFIG[state];

  const sizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg',
  };

  const iconSizeClasses = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  };

  // Icon only variant
  if (variant === 'icon') {
    return (
      <span
        className={cn('inline-flex items-center', iconSizeClasses[size], className)}
        title={showTooltip ? `${config.label}: ${config.description}` : undefined}
        role="img"
        aria-label={config.label}
      >
        {config.icon}
      </span>
    );
  }

  // Badge variant
  if (variant === 'badge') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border',
          config.bgColor,
          config.borderColor,
          config.color,
          sizeClasses[size],
          className
        )}
        title={showTooltip ? config.description : undefined}
      >
        <span className={iconSizeClasses[size]}>{config.icon}</span>
        <span className="text-xs font-medium">{config.label}</span>
      </span>
    );
  }

  // Full variant
  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-lg border',
        config.bgColor,
        config.borderColor,
        sizeClasses[size],
        className
      )}
    >
      <span className="text-lg">{config.icon}</span>
      <div className="flex flex-col">
        <span className={cn('font-medium text-sm', config.color)}>{config.label}</span>
        <span className="text-xs text-muted-foreground">{config.description}</span>
      </div>
    </div>
  );
}

/**
 * Hook to manage emotional state from SSE events or API responses.
 */
export function useEmotionalState(initialState: EmotionalState = 'neutral') {
  const [state, setState] = React.useState<EmotionalState>(initialState);
  const [memoryCount, setMemoryCount] = React.useState(0);

  const updateFromResponse = React.useCallback(
    (response: { emotional_state?: string; memory_count?: number }) => {
      if (response.emotional_state) {
        setState(response.emotional_state as EmotionalState);
      }
      if (typeof response.memory_count === 'number') {
        setMemoryCount(response.memory_count);
      }
    },
    []
  );

  const reset = React.useCallback(() => {
    setState('neutral');
    setMemoryCount(0);
  }, []);

  return {
    state,
    memoryCount,
    updateFromResponse,
    reset,
    hasMemories: memoryCount > 0,
  };
}

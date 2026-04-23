'use client';

import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface RefreshAllButtonProps {
  onClick: () => void;
  isRefreshing: boolean;
}

/**
 * Discreet "Tout rafraîchir" button shown in the section header above the cards grid.
 *
 * - Mobile (<640 px): icon only (label hidden)
 * - Desktop (≥640 px): icon + label
 * - Disabled while refreshing — overlay spinner via animate-spin
 */
export function RefreshAllButton({ onClick, isRefreshing }: RefreshAllButtonProps) {
  const { t } = useTranslation();
  const label = isRefreshing
    ? t('dashboard.briefing.refreshing')
    : t('dashboard.briefing.refresh_all');

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          disabled={isRefreshing}
          aria-label={label}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium',
            'text-muted-foreground hover:text-foreground hover:bg-muted/60',
            'transition-colors duration-200',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-1',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', isRefreshing && 'motion-safe:animate-spin')}
            strokeWidth={2}
          />
          <span className="hidden sm:inline">{label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>{t('dashboard.briefing.refresh_all_tooltip')}</TooltipContent>
    </Tooltip>
  );
}

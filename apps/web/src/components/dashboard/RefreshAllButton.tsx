'use client';

import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface RefreshAllButtonProps {
  onClick: () => void;
  isRefreshing: boolean;
}

/**
 * Discreet "Tout rafraîchir" button shown in the section header above the cards grid.
 *
 * - Compact ghost treatment, with icon and translated label at every width.
 * - Busy while refreshing, with a synchronous handler guard and retained keyboard focus
 */
export function RefreshAllButton({ onClick, isRefreshing }: RefreshAllButtonProps) {
  const { t } = useTranslation();
  const label = isRefreshing
    ? t('dashboard.briefing.refreshing')
    : t('dashboard.briefing.refresh_all');

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          type="button"
          onClick={() => {
            if (!isRefreshing) onClick();
          }}
          aria-disabled={isRefreshing}
          aria-busy={isRefreshing}
          aria-label={label}
          className="h-auto min-h-8 min-w-0 max-w-full gap-1.5 whitespace-normal px-2 py-1.5 text-xs font-medium leading-snug text-muted-foreground [&_svg]:size-3.5"
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', isRefreshing && 'motion-safe:animate-spin')}
            strokeWidth={2}
            aria-hidden="true"
          />
          <span className="min-w-0 break-words text-left">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t('dashboard.briefing.refresh_all_tooltip')}</TooltipContent>
    </Tooltip>
  );
}

'use client';

import { DashboardLink as Link } from './DashboardNavigation';
import { SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { buttonVariants } from '@/components/ui/button-variants';
import { settingsSectionHref } from '@/lib/settings-sections';

interface CustomizeBriefingButtonProps {
  /** Short locale segment (e.g. `fr`) for the localized settings href. */
  lng: string;
}

/**
 * Discreet "Customize" link beside "Refresh all" in the briefing section
 * header (UX P10). The grid has been configurable since UXR Lot 5 (B4), but
 * the capability lived buried in the settings; this surfaces it exactly where
 * it becomes relevant, deep-linking to the `briefing-grid` section.
 *
 * - Compact ghost treatment, with icon and translated label at every width.
 */
export function CustomizeBriefingButton({ lng }: CustomizeBriefingButtonProps) {
  const { t } = useTranslation();
  const label = t('dashboard.briefing.customize');

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={settingsSectionHref(lng, 'briefing-grid')}
          aria-label={label}
          className={cn(
            buttonVariants({ variant: 'ghost', size: 'sm' }),
            'h-auto min-h-8 min-w-0 max-w-full gap-1.5 whitespace-normal px-2 py-1.5 text-xs font-medium leading-snug text-muted-foreground [&_svg]:size-3.5'
          )}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
          <span className="min-w-0 break-words text-left">{label}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>{t('dashboard.briefing.customize_tooltip')}</TooltipContent>
    </Tooltip>
  );
}

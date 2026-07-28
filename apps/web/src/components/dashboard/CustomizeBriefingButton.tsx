'use client';

import Link from 'next/link';
import { SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
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
 * - Mobile (<640 px): icon only (label hidden)
 * - Desktop (>=640 px): icon + label
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
            'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium',
            'text-muted-foreground hover:text-foreground hover:bg-muted/60',
            'transition-colors duration-200',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-1'
          )}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" strokeWidth={2} />
          <span className="hidden sm:inline">{label}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>{t('dashboard.briefing.customize_tooltip')}</TooltipContent>
    </Tooltip>
  );
}

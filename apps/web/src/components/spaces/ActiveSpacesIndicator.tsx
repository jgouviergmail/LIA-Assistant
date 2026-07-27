'use client';

import { useTranslation } from 'react-i18next';
import { usePathname } from 'next/navigation';
import { Library } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useActiveSpaces } from '@/hooks/useSpaces';
import Link from 'next/link';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';
import { fallbackLng } from '@/i18n/settings';

/**
 * Compact badge showing active RAG spaces count in the chat header.
 * Clicking navigates to the spaces management page.
 */
export function ActiveSpacesIndicator() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const lng = pathname ? getLanguageFromPath(pathname) : fallbackLng;
  const { activeCount, loading } = useActiveSpaces();

  if (loading || activeCount === 0) return null;

  return (
    // The accessible name lives on the LINK and is the same at every width.
    // Below `sm` the badge shows the bare count next to an icon, so the name
    // was literally "2" — and the `title` that would have explained it is a
    // hover affordance, which touch does not have. Naming the link states what
    // the number means without costing a pixel.
    <Link
      href={buildLocalizedPath('/dashboard/spaces', lng)}
      aria-label={t('spaces.indicator_tooltip', { count: activeCount })}
    >
      <Badge
        variant="info"
        className="gap-1.5 cursor-pointer hover:bg-primary/20 transition-colors"
        title={t('spaces.indicator_tooltip', { count: activeCount })}
      >
        <Library className="h-3 w-3" aria-hidden="true" />
        <span className="hidden sm:inline">{t('spaces.indicator', { count: activeCount })}</span>
        <span className="sm:hidden">{activeCount}</span>
      </Badge>
    </Link>
  );
}

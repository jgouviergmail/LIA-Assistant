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
    <Link href={buildLocalizedPath('/dashboard/spaces', lng)}>
      <Badge
        variant="info"
        className="gap-1.5 cursor-pointer hover:bg-primary/20 transition-colors"
        title={t('spaces.indicator_tooltip', { count: activeCount })}
      >
        <Library className="h-3 w-3" />
        <span className="hidden sm:inline">{t('spaces.indicator', { count: activeCount })}</span>
        <span className="sm:hidden">{activeCount}</span>
      </Badge>
    </Link>
  );
}

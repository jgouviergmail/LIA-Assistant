'use client';

import { RefreshCw } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { HeaderActions } from '@/components/ui/section-header';
import { cn } from '@/lib/utils';
import { SmsIdentityRefresh } from './SmsIdentityRefresh';

/** The same archive actions for the page and its standalone presentation. */
export function SmsArchiveActions({
  onRefresh,
  refreshing = false,
}: {
  onRefresh: () => void;
  refreshing?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <HeaderActions>
      <Button
        variant="outline"
        aria-disabled={refreshing || undefined}
        onClick={() => {
          if (!refreshing) onRefresh();
        }}
      >
        <RefreshCw
          className={cn('h-4 w-4', refreshing && 'motion-safe:animate-spin')}
          aria-hidden="true"
        />
        {t('common.refresh')}
      </Button>
      <SmsIdentityRefresh />
    </HeaderActions>
  );
}

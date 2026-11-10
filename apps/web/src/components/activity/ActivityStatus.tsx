'use client';

import { useTranslation } from 'react-i18next';
import { History } from '@/lib/icons';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { ActivityKindTotal } from '@/types/activity';

/** Empty, unavailable and unmatched data offer different, actionable exits. */
export function ActivityEmptyState({
  lng,
  failed,
  filtered,
  retry,
  clear,
}: {
  lng: string;
  failed: boolean;
  filtered: boolean;
  retry: () => void;
  clear: () => void;
}) {
  const { t } = useTranslation();
  if (failed)
    return (
      <EmptyState
        variant="page"
        icon={History}
        reason="no-data"
        title={t('activity.unavailable_title')}
        description={t('activity.partial_warning')}
        action={{ label: t('activity.retry'), onClick: retry }}
      />
    );
  if (filtered)
    return (
      <EmptyState
        variant="page"
        icon={History}
        reason="no-data"
        title={t('activity.filter.empty')}
        description={t('activity.filter.empty_description')}
        action={{ label: t('activity.filter.clear'), onClick: clear }}
      />
    );
  return (
    <EmptyState
      variant="page"
      icon={History}
      reason="no-data"
      title={t('activity.empty_title')}
      description={t('activity.empty_description')}
      action={{ label: t('activity.empty_action'), href: settingsSectionHref(lng, 'heartbeat') }}
    />
  );
}

/** Counts are the server's exact filtered totals; the pageable prefix may be smaller. */
export function ActivityTotals({ totals }: { totals: ActivityKindTotal[] }) {
  const { t } = useTranslation();
  const visible = totals.filter(item => item.total > 0);
  if (!visible.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {visible.map(item => (
        <Badge key={item.kind} variant="default">
          {t(`activity.kinds.${item.kind}`, { count: item.total })}
        </Badge>
      ))}
      {visible.some(item => item.truncated) && (
        <span className="text-xs text-muted-foreground">{t('activity.truncated_hint')}</span>
      )}
    </div>
  );
}

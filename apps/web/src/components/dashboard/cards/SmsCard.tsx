'use client';
import { useDashboardRoute } from '../DashboardNavigation';
import { MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { getIntlLocale, isLanguage, fallbackLng } from '@/i18n/settings';
import { formatNumberLocale } from '@/lib/briefing-utils';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { CardItemRow } from './CardItemRow';
import type { CardSection, SmsData } from '@/types/briefing';
interface Props {
  section?: CardSection<SmsData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}
export function SmsCard({ section, isRefreshing, onRefresh, staggerIndex }: Props) {
  if (!section) return null;
  return (
    <BriefingCard<SmsData>
      titleKey="dashboard.briefing.cards.sms.title"
      icon={<MessageSquare className="h-5 w-5" />}
      tone="sky"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.sms.empty"
      renderContent={data => <SmsContent data={data} />}
      staggerIndex={staggerIndex}
    />
  );
}
function SmsContent({ data }: { data: SmsData }) {
  const { t, i18n } = useTranslation();
  const router = useLocalizedRouter();
  const navigate = useDashboardRoute(router.push);
  const candidate = (i18n.language || fallbackLng).split('-')[0];
  const lng = isLanguage(candidate) ? candidate : fallbackLng;
  const dates = new Intl.DateTimeFormat(getIntlLocale(lng), {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: data.timezone,
  });
  return (
    <div className="min-w-0 space-y-3">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold tabular-nums text-sky-700 dark:text-sky-300 tracking-tight">
          {formatNumberLocale(data.total, lng)}
        </span>
        <span className="text-sm text-muted-foreground">
          {t('dashboard.briefing.cards.sms.total')}
        </span>
      </div>
      <ul className="space-y-1.5" role="list">
        {(data.items ?? []).map(item => {
          const date = dates.format(new Date(item.received_at));
          const sender =
            item.display_name === item.sender
              ? item.sender
              : `${item.display_name} · ${item.sender}`;
          const excerpt = item.body_truncated ? `${item.body_excerpt}…` : item.body_excerpt;
          return (
            <CardItemRow
              key={item.id}
              ariaLabel={`${t('sms.open_message')} · ${item.display_name} · ${date}`}
              tooltip={`${excerpt}\n${sender}`}
              onSelect={() =>
                navigate(`/dashboard/settings?section=sms&message=${encodeURIComponent(item.id)}`)
              }
              contentClassName="flex flex-col gap-1.5 leading-snug"
            >
              <span className="flex items-center gap-1.5 text-xs font-medium text-sky-700 dark:text-sky-300 tabular-nums">
                <MessageSquare className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <time dateTime={item.received_at}>{date}</time>
              </span>
              <span
                className="line-clamp-2 break-words text-sm font-semibold text-foreground/90"
                dir="auto"
              >
                {excerpt}
              </span>
              <span className="line-clamp-2 break-words text-xs text-muted-foreground">
                {sender}
              </span>
            </CardItemRow>
          );
        })}
      </ul>
    </div>
  );
}

'use client';
import Link from 'next/link';
import { MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { getIntlLocale, isLanguage, fallbackLng } from '@/i18n/settings';
import { formatNumberLocale } from '@/lib/briefing-utils';
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
  const candidate = (i18n.language || fallbackLng).split('-')[0];
  const lng = isLanguage(candidate) ? candidate : fallbackLng;
  const dates = new Intl.DateTimeFormat(getIntlLocale(lng), {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: data.timezone,
  });
  return (
    <div className="min-w-0 space-y-4">
      <dl className="grid grid-cols-2 gap-4 text-center">
        <div>
          <dt className="text-xs text-muted-foreground">
            {t('dashboard.briefing.cards.sms.total')}
          </dt>
          <dd className="text-3xl font-semibold tabular-nums">
            {formatNumberLocale(data.total, lng)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            {t('dashboard.briefing.cards.sms.received')}
          </dt>
          <dd className="text-3xl font-semibold tabular-nums">
            {formatNumberLocale(data.window_total, lng)}
          </dd>
        </div>
      </dl>
      <p className="break-words text-xs text-muted-foreground">
        {dates.format(new Date(data.window_start))} – {dates.format(new Date(data.as_of))}
      </p>
      <Link
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        href={`/${lng}/dashboard/sms`}
      >
        {t('dashboard.briefing.cards.sms.open')}
      </Link>
    </div>
  );
}

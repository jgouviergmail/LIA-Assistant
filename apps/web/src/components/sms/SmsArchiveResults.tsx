'use client';
import { useTranslation } from 'react-i18next';
import { z } from '@/lib/zod';
import { ApiError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { SmsMessageList } from './SmsMessageList';
import { SmsSearchGroups, SmsSenderThreads } from './SmsSenderThreads';
import type { SmsPage, SmsSenderPage } from '@/types/sms';
import type { Language } from '@/i18n/settings';
const broadRefusal = z.object({ detail: z.object({ error_code: z.literal('QUERY_TOO_BROAD') }) });
export function SmsArchiveResults({
  messages,
  senders,
  mode,
  loading,
  error,
  lng,
  timezone,
}: {
  messages: SmsPage | null;
  senders: SmsSenderPage | undefined;
  mode: 'day' | 'sender';
  loading: boolean;
  error: Error | null;
  lng: Language;
  timezone: string;
}) {
  const { t } = useTranslation();
  const current = messages ?? senders;
  return (
    <>
      {loading && !current && <p role="status">{t('common.loading')}</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t(
            error instanceof ApiError &&
              error.status === 409 &&
              broadRefusal.safeParse(error.data).success
              ? 'sms.too_broad'
              : 'sms.unavailable'
          )}
        </p>
      )}
      {current?.total === 0 && (
        <p className="rounded-lg border p-5 text-sm text-muted-foreground">{t('sms.empty')}</p>
      )}
      {messages &&
        (mode === 'sender' ? (
          <SmsSearchGroups messages={messages.items} lng={lng} timezone={timezone} />
        ) : (
          <SmsMessageList messages={messages.items} lng={lng} timezone={timezone} />
        ))}
      {senders && <SmsSenderThreads senders={senders.items} lng={lng} timezone={timezone} />}
    </>
  );
}
export function SmsArchivePager({
  loading,
  hasPrevious,
  nextCursor,
  onPrevious,
  onNext,
}: {
  loading: boolean;
  hasPrevious: boolean;
  nextCursor?: string | null;
  onPrevious: () => void;
  onNext: (cursor: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      {hasPrevious && (
        <Button
          variant="outline"
          aria-disabled={loading}
          onClick={() => {
            if (!loading) onPrevious();
          }}
        >
          {t('common.previous')}
        </Button>
      )}
      {nextCursor && (
        <Button
          variant="outline"
          aria-disabled={loading}
          onClick={() => {
            if (!loading) onNext(nextCursor);
          }}
        >
          {t('sms.load_more')}
        </Button>
      )}
    </div>
  );
}

'use client';

import { useSearchParams } from 'next/navigation';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { Disclosure } from '@/components/ui/disclosure';
import { SmsArchive } from '@/components/sms/SmsArchive';
import { SmsFocusedMessage } from '@/components/sms/SmsFocusedMessage';

export function SmsSettingsArchive({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const message = useSearchParams().get('message');
  const focused =
    message && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(message)
      ? message
      : null;
  return (
    <Disclosure
      key={focused ?? 'archive'}
      icon={MessageSquareText}
      title={t('sms.archive')}
      defaultOpen
      surface="nested"
    >
      <div className="min-w-0 space-y-4 pt-2">
        {focused && <SmsFocusedMessage messageId={focused} lng={lng} />}
        <SmsArchive lng={lng} heading={false} />
      </div>
    </Disclosure>
  );
}

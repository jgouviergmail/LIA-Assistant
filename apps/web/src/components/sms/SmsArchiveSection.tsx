'use client';

import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { MessageSquareText } from '@/lib/icons';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { Disclosure } from '@/components/ui/disclosure';
import { SmsArchive } from '@/components/sms/SmsArchive';
import { SmsFocusedMessage } from '@/components/sms/SmsFocusedMessage';

const MESSAGE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * « Consult my SMS »: the archive, open by default, with the message a
 * notification or a card named (`?message=`) shown first and focused. A value
 * that is not a message id is never read.
 */
export function SmsArchiveSection({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const message = useSearchParams().get('message');
  const focused = message && MESSAGE_ID.test(message) ? message : null;
  const [open, setOpen] = useState(true);
  const [previousFocused, setPreviousFocused] = useState(focused);
  if (previousFocused !== focused) {
    setPreviousFocused(focused);
    if (focused) setOpen(true);
  }
  return (
    <SmsArchive
      lng={lng}
      heading={false}
      enabled={open}
      onFiltersChange={() => setOpen(true)}
      renderResults={content => (
        <Disclosure
          key={focused ?? 'archive'}
          icon={MessageSquareText}
          title={t('sms.archive')}
          defaultOpen
          open={open}
          onOpenChange={setOpen}
        >
          <div className="min-w-0 space-y-4 pt-2">
            {focused && <SmsFocusedMessage key={focused} messageId={focused} lng={lng} />}
            {content}
          </div>
        </Disclosure>
      )}
    />
  );
}

'use client';

import { useState } from 'react';
import { Info } from 'lucide-react';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { Disclosure } from '@/components/ui/disclosure';
import { discussionOpeningSchema } from '@/types/proactive-discussions';

export function DiscussionDetails({ lng, id }: { lng: Language; id: string }) {
  const { t } = useTranslation(lng);
  const [open, setOpen] = useState(false);
  const query = useApplicationAccountQuery<unknown>(
    `/proactive-discussions/openings/${id}`,
    'DiscussionDetails',
    open
  );
  const parsed = discussionOpeningSchema.safeParse(query.data);
  return (
    <Disclosure
      title={t('discussions.details_title')}
      icon={Info}
      surface="nested"
      onOpenChange={setOpen}
    >
      <div className="space-y-2 text-xs text-muted-foreground">
        <p>{t('discussions.details_hint')}</p>
        {query.loading && <p role="status">{t('common.loading')}</p>}
        {(query.error || (Boolean(query.data) && !parsed.success)) && (
          <p role="alert">{t('discussions.load_error')}</p>
        )}
        {parsed.success && (
          <>
            {parsed.data.reason && <p className="break-words">{parsed.data.reason}</p>}
            <ul className="space-y-1">
              {parsed.data.evidence.map((proof, index) => (
                <li key={`${proof.source}-${index}`}>
                  {t(`discussions.sources.${proof.source}`)} ·{' '}
                  {new Date(proof.observed_at).toLocaleDateString(getIntlLocale(lng))}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Disclosure>
  );
}

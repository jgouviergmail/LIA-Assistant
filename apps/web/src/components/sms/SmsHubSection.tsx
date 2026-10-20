'use client';
import dynamic from 'next/dynamic';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';
import { Disclosure } from '@/components/ui/disclosure';
import type { Language } from '@/i18n/settings';
const Archive = dynamic(() => import('./SmsArchive').then(module => module.SmsArchive));
export function SmsHubSection({ lng, total }: { lng: Language; total: number | null | undefined }) {
  const { t } = useTranslation();
  const { config } = useAppConfig();
  if (!capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled)) return null;
  return (
    <Disclosure
      icon={MessageSquareText}
      title={t('sms.title')}
      description={t('sms.description')}
      badge={total ?? '—'}
      className="rounded-none border-x-0 border-t-0 border-b border-border/50 bg-transparent px-0 last:border-b-0 [&>summary]:min-h-16 [&>summary]:py-4"
      badgeClassName={
        total == null ? undefined : 'border border-primary/20 bg-primary/10 text-primary'
      }
    >
      <div className="py-4">
        <Archive lng={lng} heading={false} limit={10} />
      </div>
    </Disclosure>
  );
}

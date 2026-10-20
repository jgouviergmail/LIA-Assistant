'use client';
import { useSearchParams } from 'next/navigation';
import { FeatureErrorBoundary } from '@/components/errors';
import { SmsArchive } from '@/components/sms/SmsArchive';
import { SmsFocusedMessage } from '@/components/sms/SmsFocusedMessage';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useTranslation } from '@/i18n/client';
import { capabilityEnabled } from '@/lib/capability-state';
export default function SmsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const { user } = useAuth();
  const message = useSearchParams().get('message');
  const focused =
    message && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(message)
      ? message
      : null;
  const enabled = capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled);
  return (
    <FeatureErrorBoundary feature="sms">
      <div className="mx-auto w-full max-w-5xl space-y-6 p-4 sm:p-6">
        {enabled ? (
          <>
            {focused && (
              <SmsFocusedMessage key={`${user?.id}:${focused}`} messageId={focused} lng={lng} />
            )}
            <SmsArchive lng={lng} />
          </>
        ) : (
          <p role="status">{t('sms.unavailable')}</p>
        )}
      </div>
    </FeatureErrorBoundary>
  );
}

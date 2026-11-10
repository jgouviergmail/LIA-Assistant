'use client';

/**
 * SmsWorkspace — the « SMS » page (owner request 2026-10-31): the three views a
 * person uses on the SMS their phone forwards — consult them, block a sender,
 * erase — behind the header's « SMS », drawn like the other destinations, with
 * no settings panel behind them. How SMS reach LIA (the ingestion tokens, the
 * push, the assistant's access, the statistics) stays in Settings › SMS.
 *
 * Offered where the instance offers SMS now (`smsAvailable`, the operator's
 * switch included); elsewhere the page says so and reads nothing. Changes use
 * the existing command writer: one message is deleted by its explicit click,
 * other scopes are reviewed in `SmsConfirmation`. Views re-read in place
 * when a change lands (the source-owned `sms` resource).
 */
import { MessageSquareText } from '@/lib/icons';

import { SmsArchiveErasure } from '@/components/sms/SmsArchiveErasure';
import { SmsArchiveSection } from '@/components/sms/SmsArchiveSection';
import { SmsArchiveActions } from '@/components/sms/SmsArchiveActions';
import { SmsBlockedSenders } from '@/components/sms/SmsBlockedSenders';
import { SmsConfirmation } from '@/components/sms/SmsConfirmation';
import { SmsErasureProvider } from '@/components/sms/SmsErasure';
import { EmptyState } from '@/components/ui/empty-state';
import { SectionHeader } from '@/components/ui/section-header';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useSmsBlockedSenders } from '@/hooks/useSmsBlockedSenders';
import { useSmsManagement } from '@/hooks/useSmsManagement';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { publishApplicationResources } from '@/lib/application-resources';
import { smsAvailable } from '@/lib/sms/availability';

export function SmsWorkspace({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const { config } = useAppConfig();
  const { user } = useAuth();
  const offered = smsAvailable(config);
  const owner = user?.id;
  return (
    <div className="min-w-0 space-y-6">
      <SectionHeader
        level={1}
        icon={MessageSquareText}
        title={t('sms.title')}
        description={t('sms.description')}
        actions={
          offered && owner ? (
            <SmsArchiveActions
              onRefresh={() => publishApplicationResources(owner, new Set(['sms']))}
            />
          ) : null
        }
      />
      {offered ? (
        <SmsViews key={owner ?? 'signed-out'} lng={lng} />
      ) : (
        config && <EmptyState icon={MessageSquareText} description={t('sms.not_offered')} />
      )}
    </div>
  );
}

function SmsViews({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const { user } = useAuth();
  const blocked = useSmsBlockedSenders();
  const actions = useSmsManagement();
  return (
    <div className="min-w-0 space-y-4" aria-busy={actions.busy || undefined}>
      {(blocked.blocks.error || actions.error) && (
        <p role="alert" className="text-sm text-destructive">
          {t('sms.unavailable')}
        </p>
      )}
      {actions.uncertain && (
        <p role="alert" className="text-sm text-destructive">
          {t('sms.unknown_result')}
        </p>
      )}
      <SmsErasureProvider
        value={{
          busy: actions.busy,
          request: scope => {
            if ('message_ids' in scope) void actions.eraseMessage(scope.message_ids[0]);
            else void actions.propose('sms_messages.delete', scope);
          },
        }}
      >
        <SmsArchiveSection lng={lng} />
      </SmsErasureProvider>
      <SmsBlockedSenders blocked={blocked} actions={actions} />
      <SmsArchiveErasure actions={actions} timezone={user?.timezone || 'Europe/Paris'} />
      <SmsConfirmation actions={actions} />
    </div>
  );
}

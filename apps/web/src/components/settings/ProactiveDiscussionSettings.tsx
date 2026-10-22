'use client';

import { useState } from 'react';
import { Activity, Database, MessagesSquare } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useProactiveDiscussions } from '@/hooks/useProactiveDiscussions';
import { useTranslation } from '@/i18n/client';
import type { BaseSettingsProps } from '@/types/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Disclosure } from '@/components/ui/disclosure';
import { Button } from '@/components/ui/button';
import { DiscussionControls } from './DiscussionControls';
import { DiscussionContext, DiscussionContextStatus } from './DiscussionContext';
import { DiscussionHistory } from './DiscussionHistory';
import { discussionSettingsSchema } from '@/types/proactive-discussions';

export function ProactiveDiscussionSettings({ lng }: BaseSettingsProps) {
  const { user } = useAuth();
  return <AccountDiscussionSettings key={user?.id ?? 'signed-out'} lng={lng} />;
}

function AccountDiscussionSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const [contextOpen, setContextOpen] = useState(false);
  const [dataOpen, setDataOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  // Either panel reads the context: the status and the data are one read.
  const controls = useProactiveDiscussions(contextOpen || dataOpen);
  const parsed = discussionSettingsSchema.safeParse(controls.settings.data);
  const data = parsed.success ? parsed.data : undefined;
  return (
    <SettingsSection
      value="proactive-discussions"
      title={t('discussions.title')}
      description={t('discussions.description')}
      icon={MessagesSquare}
    >
      <div className="min-w-0 space-y-5">
        {(controls.error ||
          controls.settings.error ||
          controls.context.error ||
          (controls.settings.data && !data)) && (
          <div role="alert" className="space-y-2 text-sm text-destructive">
            <p>{t('discussions.load_error')}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void controls.refresh().catch(() => undefined);
              }}
            >
              {t('common.retry')}
            </Button>
          </div>
        )}
        {!data && controls.settings.loading && <p role="status">{t('common.loading')}</p>}
        {data && (
          <>
            {!data.producer_enabled && (
              <p role="status" className="text-sm text-muted-foreground">
                {t('discussions.producer_off')}
              </p>
            )}
            {data.policy.enabled && !data.budget_configured && (
              <p role="status" className="text-sm text-muted-foreground">
                {t('discussions.budget_missing')}
              </p>
            )}
            <DiscussionControls
              lng={lng}
              settings={data}
              busy={controls.saving}
              update={controls.update}
            />
          </>
        )}
        {/* Two panels (owner request 2026-10-21): where the context work
            stands, then the data it holds. */}
        <Disclosure
          title={t('discussions.context_title')}
          icon={Activity}
          surface="nested"
          onOpenChange={setContextOpen}
        >
          <DiscussionContextStatus lng={lng} controls={controls} />
        </Disclosure>
        <Disclosure
          title={t('discussions.context_data_title')}
          icon={Database}
          surface="nested"
          onOpenChange={setDataOpen}
        >
          <DiscussionContext lng={lng} controls={controls} />
        </Disclosure>
        <Disclosure
          title={t('discussions.history_title')}
          icon={MessagesSquare}
          surface="nested"
          onOpenChange={setHistoryOpen}
        >
          <DiscussionHistory lng={lng} open={historyOpen} />
        </Disclosure>
      </div>
    </SettingsSection>
  );
}

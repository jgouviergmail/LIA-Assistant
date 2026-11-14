'use client';

import { KeyRound, Link2 } from '@/lib/icons';
import { useTranslation } from 'react-i18next';

import { CopyValueField } from '@/components/settings/CopyValueField';
import { Button } from '@/components/ui/button';
import { FormSection } from '@/components/ui/form-section';

interface RoutineWebhookFieldsProps {
  /** The stored routine's address, when it already runs on calls; null before. */
  webhookUrl: string | null;
  /** Draw a new secret (the caller confirms and shows it). */
  onDrawSecret: () => void;
  /** A new secret is being drawn. */
  drawing: boolean;
}

/**
 * The form's section for a routine another system starts (ADR-386).
 *
 * Nothing here is typed: the address and the secret are the server's. Before
 * the routine runs on calls, the section says what saving will do; once it
 * does, it shows the address and offers a new secret — the only way to see one
 * again, since a secret is shown once.
 */
export function RoutineWebhookFields({
  webhookUrl,
  onDrawSecret,
  drawing,
}: RoutineWebhookFieldsProps) {
  const { t } = useTranslation();
  return (
    <FormSection icon={Link2} title={t('scheduled_actions.webhook.section')}>
      {webhookUrl ? (
        <>
          <CopyValueField
            id="sa-webhook-url"
            label={t('scheduled_actions.webhook.address')}
            value={webhookUrl}
            copyLabel={t('scheduled_actions.webhook.copy_address')}
            copiedMessage={t('scheduled_actions.webhook.copied')}
          />
          <div className="space-y-3">
            <p id="sa-webhook-draw-hint" className="text-xs text-muted-foreground">
              {t('scheduled_actions.webhook.draw_hint')}
            </p>
            <Button
              type="button"
              variant="outline"
              isLoading={drawing}
              aria-describedby="sa-webhook-draw-hint"
              onClick={onDrawSecret}
            >
              <KeyRound className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('scheduled_actions.webhook.draw_new')}
            </Button>
          </div>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">{t('scheduled_actions.webhook.hint_new')}</p>
      )}
      <p className="text-xs text-muted-foreground">{t('scheduled_actions.webhook.hint_served')}</p>
    </FormSection>
  );
}

'use client';

import { useTranslation } from 'react-i18next';
import { useRef, type ComponentType } from 'react';
import { ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StepUpDialog } from '@/components/auth/StepUpDialog';
import {
  ApplicationExportDownloadCard,
  applicationExportTitles,
} from '@/components/chat/ApplicationExportDownloadCard';
import { useApplicationCommandResume } from '@/hooks/useApplicationCommandResume';
import { useAuth } from '@/hooks/useAuth';
import { ApplicationHealthTokenCard } from '@/components/chat/ApplicationHealthTokenCard';
import { ApplicationDocumentUploadCard } from '@/components/chat/ApplicationDocumentUploadCard';
import { ApplicationSkillFileUploadCard } from '@/components/chat/ApplicationSkillFileUploadCard';
import { ApplicationPluginFileUploadCard } from '@/components/chat/ApplicationPluginFileUploadCard';
import { ApplicationPersonalMCPConfigurationCard } from '@/components/chat/ApplicationPersonalMCPConfigurationCard';
import { ApplicationPersonalMCPOAuthCard } from '@/components/chat/ApplicationPersonalMCPOAuthCard';
import { ApplicationRecordingDeviceCard } from '@/components/chat/ApplicationRecordingDeviceCard';
import { z } from '@/lib/zod';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import {
  secureActionPresentation,
  type SecureActionPresentation,
} from '@/lib/application-secure-actions';

const references = z.array(z.object({ command_id: z.string().uuid() }).strict());
const copy = 'settings.application_tools';

type InteractionCardProps = {
  status: ApplicationCommandStatus;
  checkResult: () => Promise<void>;
  readError: Error | null;
};
const privateInteractionCards: Partial<Record<string, ComponentType<InteractionCardProps>>> = {
  'knowledge_document.upload': ApplicationDocumentUploadCard,
  'skill_file.upload': ApplicationSkillFileUploadCard,
  'plugin_file.upload': ApplicationPluginFileUploadCard,
  'health_token.create': ApplicationHealthTokenCard,
  'personal_mcp.configuration': ApplicationPersonalMCPConfigurationCard,
  'personal_mcp.oauth_authorize': ApplicationPersonalMCPOAuthCard,
};

function resultKey(status: ApplicationCommandStatus): string {
  if (status.phase === 'committed') return 'secure_complete';
  if (['claimed', 'resuming'].includes(status.phase)) return 'secure_running';
  if (status.phase === 'expired') return 'secure_expired';
  if (status.outcome?.error_code === 'COMPLETION_UNKNOWN') return 'secure_unknown';
  if (status.phase === 'failed' || status.phase === 'conflict') return 'secure_failed';
  return 'secure_waiting';
}

function outcomeKey(
  status: ApplicationCommandStatus,
  presentation: SecureActionPresentation,
  count: number | undefined
): string {
  if (status.phase === 'committed')
    return presentation.completed ?? (count === undefined ? 'secure_done' : 'secure_complete');
  if (status.outcome?.committed && presentation.committedFailure)
    return presentation.committedFailure;
  return resultKey(status);
}

function revokedSessionCount(status: ApplicationCommandStatus): number | undefined {
  const count = status.outcome?.values.revoked_sessions;
  return typeof count === 'number' && Number.isSafeInteger(count) && count >= 0 ? count : undefined;
}

function ApplicationInteractionCard({ commandId }: { commandId: string }) {
  const action = useApplicationCommandResume(commandId);
  const { status } = action;
  if (status?.operation_id === 'meeting_device.control')
    return (
      <ApplicationRecordingDeviceCard commandId={commandId} observation={action.observation} />
    );
  const PrivateCard =
    status && Object.hasOwn(privateInteractionCards, status.operation_id)
      ? privateInteractionCards[status.operation_id]
      : null;
  if (status && PrivateCard)
    return (
      <PrivateCard status={status} checkResult={action.checkResult} readError={action.readError} />
    );
  if (status && Object.hasOwn(applicationExportTitles, status.operation_id))
    return (
      <ApplicationExportDownloadCard
        status={status}
        checkResult={action.checkResult}
        readError={action.readError}
      />
    );
  const presentation = status && secureActionPresentation(status.operation_id);
  if (!status || !presentation) return null;
  return <SecureInteractionCard status={status} presentation={presentation} action={action} />;
}

function SecureInteractionCard({
  status,
  presentation,
  action,
}: {
  status: ApplicationCommandStatus;
  presentation: SecureActionPresentation;
  action: ReturnType<typeof useApplicationCommandResume>;
}) {
  const { t } = useTranslation();
  const checkButton = useRef<HTMLButtonElement>(null);
  const { mode } = action;
  const safeCount = revokedSessionCount(status);
  const waiting =
    status.phase === 'waiting' && status.interaction?.kind === 'secure' && mode !== 'uncertain';
  const message =
    mode === 'uncertain' ? 'secure_unknown' : outcomeKey(status, presentation, safeCount);
  return (
    <section
      className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t(`${copy}.${presentation.title}`)}
      aria-busy={mode === 'busy'}
    >
      <h3 className="flex items-start gap-2 text-sm font-medium">
        <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
        {t(`${copy}.${presentation.title}`)}
      </h3>
      <p className="mt-1 break-words text-sm text-muted-foreground" role="status">
        {t(`${copy}.${message}`, { count: safeCount })}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {waiting && (
          <Button
            size="sm"
            aria-disabled={mode === 'busy'}
            onClick={() => {
              void action.resume().then(current => {
                if (current) checkButton.current?.focus();
              });
            }}
          >
            {t(`${copy}.secure_continue`)}
          </Button>
        )}
        <Button
          ref={checkButton}
          size="sm"
          variant="outline"
          aria-disabled={mode === 'busy'}
          onClick={() => {
            if (mode !== 'busy') void action.checkResult();
          }}
        >
          {t(`${copy}.secure_check`)}
        </Button>
      </div>
      {action.readError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {t(`${copy}.secure_read_failed`)}
        </p>
      )}
      <StepUpDialog
        key={action.dialogKey}
        open={action.stepUpOpen}
        onVerified={action.onVerified}
        onCancel={action.onCancel}
      />
    </section>
  );
}

export function ApplicationInteractionCards({ metadata }: { metadata?: Record<string, unknown> }) {
  const { user } = useAuth();
  const parsed = references.safeParse(metadata?.application_interactions);
  if (!parsed.success) return null;
  const ids = [...new Set(parsed.data.map(item => item.command_id))];
  return (
    <>
      {ids.map(id => (
        <ApplicationInteractionCard key={`${user?.id}:${id}`} commandId={id} />
      ))}
    </>
  );
}

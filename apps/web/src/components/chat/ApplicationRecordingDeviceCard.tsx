'use client';

import { useTranslation } from 'react-i18next';
import { useRef } from 'react';
import { Mic } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useApplicationDeviceCommand } from '@/hooks/useApplicationDeviceCommand';
import type { useApplicationCommandStatus } from '@/hooks/useApplicationCommandStatus';

const copy = 'settings.application_tools';

export function ApplicationRecordingDeviceCard({
  commandId,
  observation,
}: {
  commandId: string;
  observation: ReturnType<typeof useApplicationCommandStatus>;
}) {
  const { t } = useTranslation();
  const checkButton = useRef<HTMLButtonElement>(null);
  const action = useApplicationDeviceCommand(commandId, observation);
  const status = action.status;
  if (!status) return null;
  const waiting =
    status.phase === 'waiting' &&
    status.interaction?.kind === 'device' &&
    action.mode !== 'uncertain';
  const message =
    action.mode === 'uncertain' || status.outcome?.error_code === 'COMPLETION_UNKNOWN'
      ? 'secure_unknown'
      : status.phase === 'committed'
        ? 'device_recording_done'
        : status.phase === 'waiting'
          ? 'device_recording_waiting'
          : status.phase === 'expired'
            ? 'secure_expired'
            : ['claimed', 'resuming'].includes(status.phase)
              ? 'secure_running'
              : 'secure_failed';
  return (
    <section
      data-application-action-priority="true"
      className="mt-2 min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t(`${copy}.device_recording_title`)}
      aria-busy={action.mode === 'busy'}
    >
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <Mic className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${copy}.device_recording_title`)}
      </h3>
      <p className="mt-1 break-words text-sm text-muted-foreground" role="status">
        {t(`${copy}.${message}`)}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {waiting && (
          <Button
            size="sm"
            aria-disabled={action.mode === 'busy'}
            onClick={() => {
              void action.execute().then(current => {
                if (current) checkButton.current?.focus();
              });
            }}
          >
            {t(`${copy}.device_recording_execute`)}
          </Button>
        )}
        <Button
          ref={checkButton}
          size="sm"
          variant="outline"
          onClick={() => {
            void action.checkResult();
          }}
        >
          {t(`${copy}.secure_check`)}
        </Button>
      </div>
    </section>
  );
}

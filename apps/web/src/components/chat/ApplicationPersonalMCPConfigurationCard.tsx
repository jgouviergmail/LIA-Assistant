'use client';

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { MCPServerFormFields } from '@/components/settings/MCPServerFormFields';
import { useApplicationPersonalMCPConfiguration } from '@/hooks/useApplicationPersonalMCPConfiguration';
import { personalMCPConfigurationMessage } from '@/lib/application-personal-mcp-configuration';
import { isMCPServerFormValid } from '@/lib/mcp-server-form';
import type { ApplicationCommandStatus } from '@/types/application-commands';

interface Props {
  status: ApplicationCommandStatus;
  checkResult: () => Promise<void>;
  readError: Error | null;
}
const copy = 'settings.application_tools';

export function ApplicationPersonalMCPConfigurationCard({ status, checkResult, readError }: Props) {
  const { t } = useTranslation();
  const action = useApplicationPersonalMCPConfiguration(status, checkResult);
  const checkButton = useRef<HTMLButtonElement>(null);
  const busy = action.mode === 'busy';
  const canSave =
    action.waiting &&
    action.ready &&
    action.mode === 'idle' &&
    isMCPServerFormValid(action.form, !!action.server);
  const message = personalMCPConfigurationMessage(status, action.mode, action.expired);
  return (
    <section
      className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t(`${copy}.mcp_configuration_title`)}
      aria-busy={busy}
    >
      <h3 className="flex items-start gap-2 text-sm font-medium">
        <Server className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${copy}.mcp_configuration_title`)}
      </h3>
      <p role="status" className="mt-1 break-words text-sm text-muted-foreground">
        {t(`${copy}.${message}`)}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {action.waiting && action.mode === 'idle' && (
          <Button
            size="sm"
            onClick={() => {
              void action.showForm();
            }}
          >
            {t(`${copy}.mcp_configuration_open`)}
          </Button>
        )}
        <Button
          ref={checkButton}
          size="sm"
          variant="outline"
          aria-disabled={busy}
          onClick={() => {
            if (!busy) void checkResult();
          }}
        >
          {t(`${copy}.secure_check`)}
        </Button>
      </div>
      {readError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {t(`${copy}.secure_read_failed`)}
        </p>
      )}
      <Dialog
        open={action.open}
        onOpenChange={open => {
          if (!open) action.closeForm();
        }}
      >
        <DialogContent
          className="sm:max-w-[560px] max-h-[90dvh] overflow-y-auto"
          onCloseAutoFocus={event => {
            event.preventDefault();
            checkButton.current?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Server className="h-4 w-4 text-primary" aria-hidden="true" />
              {t(`${copy}.mcp_configuration_title`)}
            </DialogTitle>
            <DialogDescription>{t(`${copy}.mcp_configuration_private`)}</DialogDescription>
          </DialogHeader>
          {action.loading && <LoadingSpinner label={t('common.loading')} />}
          {action.loadFailed && (
            <div role="alert" className="space-y-3">
              <p className="text-sm text-destructive">{t(`${copy}.secure_read_failed`)}</p>
              <Button
                variant="outline"
                onClick={() => {
                  void action.showForm();
                }}
              >
                {t('common.retry')}
              </Button>
            </div>
          )}
          {action.ready && (
            <fieldset disabled={busy} className="min-w-0 border-0 p-0">
              <MCPServerFormFields
                form={action.form}
                setForm={action.setForm}
                editingServer={action.server}
                t={t}
              />
            </fieldset>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={action.closeForm}>
              {t('common.cancel')}
            </Button>
            <Button
              aria-disabled={!canSave}
              onClick={() => {
                if (canSave)
                  void action.save(() => {
                    checkButton.current?.focus();
                  });
              }}
            >
              {busy && <LoadingSpinner className="h-4 w-4" />}
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

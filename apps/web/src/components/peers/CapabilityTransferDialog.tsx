'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileMinus, Files, Send } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useCapabilityRecipients } from '@/hooks/useCapabilityRecipients';
import { useCapabilityTransfer } from '@/hooks/useCapabilityTransfer';
import { peersErrorCode } from '@/components/settings/peers/peers-error-messages';
import type { CapabilitySelection, CapabilityTransfer } from '@/lib/capability-sharing';
import { PeerRecipientList } from './PeerRecipientList';

const ERROR_KEYS: Record<string, string> = {
  peers_capability_changed: 'changed',
  peers_capability_expired: 'expired',
  peers_capability_busy: 'busy',
  peers_capability_quota_reached: 'quota',
  peers_capability_name_conflict: 'conflict',
  peers_capability_recipient_changed: 'recipient_changed',
  peers_capability_not_shareable: 'not_shareable',
};

function Inventory({ preview }: { preview: CapabilityTransfer }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      {preview.files.length > 0 && (
        <div>
          <h3 className="mb-1 flex items-center gap-2 text-sm font-medium">
            <Files className="h-4 w-4 text-primary" aria-hidden />
            {t('settings.capability_share.files')}
          </h3>
          <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2 text-xs">
            {preview.files.map(file => (
              <li key={file.path} className="flex justify-between gap-3">
                <span className="min-w-0 break-words">{file.path}</span>
                <span className="shrink-0 text-foreground/80">
                  {t('settings.capability_share.bytes', { size: file.size })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {preview.omitted.length > 0 && (
        <div>
          <h3 className="mb-1 flex items-center gap-2 text-sm font-medium">
            <FileMinus className="h-4 w-4 text-primary" aria-hidden />
            {t('settings.capability_share.omitted')}
          </h3>
          <ul className="max-h-24 overflow-y-auto text-xs text-foreground/80">
            {preview.omitted.map(path => (
              <li className="break-words" key={path}>
                {path}
              </li>
            ))}
          </ul>
        </div>
      )}
      {preview.requires_credentials && (
        <p className="text-sm text-foreground/80">{t('settings.capability_share.credentials')}</p>
      )}
    </div>
  );
}

function Outcome({ receipt }: { receipt: CapabilityTransfer }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <p className="text-sm font-medium">
        {t(`settings.capability_share.status.${receipt.status}`)}
      </p>
      <ul className="space-y-1">
        {receipt.components.map(component => (
          <li
            key={`${component.kind}:${component.key}`}
            className="flex flex-wrap items-center justify-between gap-2 text-xs"
          >
            <span className="min-w-0 break-words">{component.key}</span>
            <Badge
              variant={
                component.installed ? 'default' : component.error_code ? 'destructive' : 'outline'
              }
              className="text-xs"
            >
              {t(
                `settings.capability_share.${component.installed ? 'component_installed' : 'component_missing'}`
              )}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

type TransferController = ReturnType<typeof useCapabilityTransfer>;

function TransferReview({ preview, outcome }: Pick<TransferController, 'preview' | 'outcome'>) {
  const stage = useRef<HTMLDivElement>(null);
  const phase = outcome?.status;
  const previewId = preview?.id;
  useEffect(() => {
    if (previewId) stage.current?.focus();
  }, [previewId, phase]);
  if (!preview) return null;
  return (
    <div
      ref={stage}
      tabIndex={-1}
      role="region"
      aria-label={preview.name}
      className="space-y-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Inventory preview={preview} />
      {outcome && <Outcome receipt={outcome} />}
    </div>
  );
}

function ConfirmationActions({
  transfer,
  preview,
}: {
  transfer: TransferController;
  preview: CapabilityTransfer;
}) {
  const { t } = useTranslation();
  const { outcome, pending } = transfer;
  const retry = outcome?.status === 'partial' || outcome?.status === 'failed';
  const sendable = !outcome || retry || outcome.status === 'preparing';
  return (
    <>
      <Button variant="outline" isLoading={pending} onClick={() => transfer.reset()}>
        {t('settings.capability_share.new_preview')}
      </Button>
      {outcome?.status !== 'installed' && (
        <Button
          variant="outline"
          isLoading={pending}
          onClick={() => void transfer.refresh(preview)}
        >
          {t('settings.capability_share.refresh')}
        </Button>
      )}
      {sendable && (
        <Button isLoading={pending} onClick={() => void transfer.send(preview)}>
          {t(`settings.capability_share.${retry ? 'retry' : 'send'}`)}
        </Button>
      )}
    </>
  );
}

function TransferButtons({
  transfer,
  selected,
  onClose,
}: {
  transfer: TransferController;
  selected: string | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <DialogFooter className="gap-2 sm:flex-wrap sm:space-x-0">
      <Button variant="outline" onClick={onClose}>
        {t('common.close')}
      </Button>
      {transfer.preview ? (
        <ConfirmationActions transfer={transfer} preview={transfer.preview} />
      ) : (
        <Button
          disabled={!selected}
          isLoading={transfer.pending}
          onClick={() => {
            if (selected) void transfer.prepare(selected);
          }}
        >
          {t('settings.capability_share.preview')}
        </Button>
      )}
    </DialogFooter>
  );
}

export function CapabilityTransferDialog({
  source,
  onClose,
}: {
  source: CapabilitySelection;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const peers = useCapabilityRecipients();
  const transfer = useCapabilityTransfer(source);
  const [connection, setConnection] = useState<string | null>(null);
  const group = useId();
  const selected = peers.recipients.some(peer => peer.id === connection) ? connection : null;
  const code = peersErrorCode(transfer.error);
  return (
    <Dialog
      open
      onOpenChange={open => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-4 w-4 text-primary" aria-hidden />
            {t('settings.capability_share.title')}
          </DialogTitle>
          <DialogDescription>{t('settings.capability_share.description')}</DialogDescription>
        </DialogHeader>
        <p className="break-words text-sm font-medium">{transfer.preview?.name ?? source.name}</p>
        {source.kind !== 'mcp' && (
          <p className="text-sm text-foreground/80">
            {t('settings.capability_share.execution_notice')}
          </p>
        )}
        <fieldset disabled={transfer.pending || !!transfer.preview} className="space-y-2">
          <legend className="text-sm font-medium">
            {t('settings.capability_share.recipient')}
          </legend>
          <PeerRecipientList
            loading={peers.loading}
            failed={peers.error !== null}
            recipients={peers.recipients}
            groupName={group}
            selected={connection}
            onSelect={setConnection}
          />
        </fieldset>
        <TransferReview preview={transfer.preview} outcome={transfer.outcome} />
        {transfer.error && (
          <p role="alert" className="text-sm text-destructive">
            {t(`settings.capability_share.errors.${(code && ERROR_KEYS[code]) || 'generic'}`)}
          </p>
        )}
        {transfer.pending && transfer.preview && (
          <p className="text-xs text-foreground/80" role="status">
            {t('settings.capability_share.pending_notice')}
          </p>
        )}
        <TransferButtons transfer={transfer} selected={selected} onClose={onClose} />
      </DialogContent>
    </Dialog>
  );
}

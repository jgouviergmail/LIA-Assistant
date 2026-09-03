/**
 * The Gmail labels a space follows (ADR-262), with link/unlink/sync actions.
 *
 * Mirrors DriveSourcesList; the destructive confirmation is the shared
 * UnlinkDriveSourceConfirm dialog, whose wording is passed in — one dialog,
 * two sources.
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Mail, TagsIcon } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { MailLabelPickerDialog } from '@/components/spaces/MailLabelPickerDialog';
import { MailSourceCard } from '@/components/spaces/MailSourceCard';
import { UnlinkSourceConfirm } from '@/components/spaces/UnlinkSourceConfirm';
import type { RAGMailSource } from '@/types/rag-spaces';

interface MailSourcesListProps {
  spaceId: string;
  sources: RAGMailSource[];
  onLink: (labelId: string, labelName: string) => Promise<unknown>;
  onUnlink: (sourceId: string, deleteDocuments: boolean) => void;
  onSync: (sourceId: string) => void;
  linking?: boolean;
  syncing?: boolean;
}

export function MailSourcesList({
  spaceId,
  sources,
  onLink,
  onUnlink,
  onSync,
  linking,
  syncing,
}: MailSourcesListProps) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [unlinkSource, setUnlinkSource] = useState<RAGMailSource | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-medium">{t('spaces.mail.title')}</h3>
        </div>
        <Button
          size="sm"
          className="gap-1.5"
          onClick={() => setPickerOpen(true)}
          isLoading={linking}
        >
          <TagsIcon className="h-3.5 w-3.5" aria-hidden="true" />
          {t('spaces.mail.link_label')}
        </Button>
      </div>

      {sources.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center">
          <p className="text-sm text-muted-foreground">{t('spaces.mail.empty')}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map(source => (
            <MailSourceCard
              key={source.id}
              source={source}
              onSync={onSync}
              onUnlink={id => {
                const found = sources.find(s => s.id === id);
                if (found) setUnlinkSource(found);
              }}
              syncing={syncing}
            />
          ))}
        </div>
      )}

      <MailLabelPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        spaceId={spaceId}
        linkedLabelIds={sources.map(source => source.label_id)}
        onSelect={(labelId, labelName) => {
          void onLink(labelId, labelName);
        }}
      />

      {unlinkSource && (
        <UnlinkSourceConfirm
          open
          onOpenChange={open => {
            if (!open) setUnlinkSource(null);
          }}
          title={t('spaces.mail.unlink_confirm_title')}
          message={t('spaces.mail.unlink_confirm_message', { name: unlinkSource.label_name })}
          deleteDocumentsLabel={t('spaces.mail.unlink_delete_docs')}
          confirmLabel={t('spaces.mail.unlink')}
          onConfirm={deleteDocuments => {
            onUnlink(unlinkSource.id, deleteDocuments);
            setUnlinkSource(null);
          }}
        />
      )}
    </div>
  );
}

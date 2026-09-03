'use client';

/**
 * Moving documents to another space (ADR-259): the user's other spaces with
 * their document counts, a submit refused until one is chosen, and an honest
 * empty state when there is nowhere to move to. The choice lives inside the
 * content, which Radix unmounts on close, so reopening starts clean.
 */

import { useId, useState } from 'react';
import { FolderInput } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RAGSpace } from '@/types/rag-spaces';

export interface MoveDocumentsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The spaces a document may move to (never the current one). */
  spaces: RAGSpace[];
  /** How many documents are about to move. */
  count: number;
  isMoving: boolean;
  onSubmit: (targetSpaceId: string) => void;
}

function MoveForm({
  spaces,
  isMoving,
  onSubmit,
}: Pick<MoveDocumentsDialogProps, 'spaces' | 'isMoving' | 'onSubmit'>) {
  const { t } = useTranslation();
  const selectId = useId();
  const [target, setTarget] = useState<string | null>(null);
  const blocked = target === null || isMoving;

  if (spaces.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {t('spaces.documents.move_dialog.none_available')}
      </p>
    );
  }
  return (
    <>
      <div className="space-y-3">
        <Label htmlFor={selectId}>{t('spaces.documents.move_dialog.target_label')}</Label>
        <Select value={target ?? ''} onValueChange={setTarget}>
          <SelectTrigger id={selectId} className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {spaces.map(space => (
              <SelectItem key={space.id} value={space.id}>
                {space.name} ·{' '}
                {t('spaces.documents.move_dialog.target_count', { count: space.document_count })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <DialogFooter className="mt-6">
        <Button
          type="button"
          aria-disabled={blocked}
          isLoading={isMoving}
          loadingText={t('spaces.documents.move_dialog.submit')}
          onClick={() => {
            if (!blocked && target !== null) onSubmit(target);
          }}
        >
          <FolderInput className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('spaces.documents.move_dialog.submit')}
        </Button>
      </DialogFooter>
    </>
  );
}

export function MoveDocumentsDialog({
  open,
  onOpenChange,
  spaces,
  count,
  isMoving,
  onSubmit,
}: MoveDocumentsDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('spaces.documents.move_dialog.title')}</DialogTitle>
          <DialogDescription>
            {t('spaces.documents.selected_count', { count })} —{' '}
            {t('spaces.documents.move_dialog.description')}
          </DialogDescription>
        </DialogHeader>
        <MoveForm spaces={spaces} isMoving={isMoving} onSubmit={onSubmit} />
      </DialogContent>
    </Dialog>
  );
}

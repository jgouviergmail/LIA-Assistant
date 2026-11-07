'use client';

/**
 * KeepDialog — a file kept in a knowledge space (ADR-372, lot 5).
 *
 * The person picks the space; the server reads the file itself, and the space judges it as it
 * judges an upload. Spaces another domain manages take nothing by hand, so they are not offered.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient, { ApiError } from '@/lib/api-client';
import { ASSIST_PATHS } from '@/lib/workbench/assist';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { RAGSpace } from '@/types/rag-spaces';

import type { Say } from './lines';
import { ToolDialogHeader } from '../ToolForm';

/** What is kept: a drive's file, or a message's attachment. */
export type Keeping =
  | { kind: 'file'; name: string; file_id: string }
  | {
      kind: 'attachment';
      name: string;
      filename: string;
      message_id: string;
      attachment_id: string | null;
    };

interface SpacesAnswer {
  spaces: RAGSpace[];
}

/** What a space answers past the Tools' own refusals: each status means one thing there. */
const SPACE_REFUSALS: Readonly<Record<number, string>> = {
  400: 'workbench.assist.keep.full',
  413: 'workbench.assist.keep.too_large',
  415: 'workbench.assist.keep.wrong_type',
};

function refusalWords(refused: unknown, t: Say): string {
  const refusal = workbenchRefusal(refused);
  if (refusal) return t(refusal.key, refusal.values);
  const status = refused instanceof ApiError ? refused.status : 0;
  return t(SPACE_REFUSALS[status] ?? 'workbench.assist.keep.failed');
}

export interface KeepDialogProps {
  lng: Language;
  what: Keeping;
  onClose: () => void;
}

function keepRequest(what: Keeping, spaceId: string): [string, object] {
  if (what.kind === 'file') {
    return [ASSIST_PATHS.keepFile, { space_id: spaceId, file_id: what.file_id }];
  }
  return [
    ASSIST_PATHS.keepAttachment,
    {
      space_id: spaceId,
      message_id: what.message_id,
      attachment_id: what.attachment_id,
      filename: what.filename,
    },
  ];
}

export function KeepDialog({ lng, what, onClose }: KeepDialogProps) {
  const { t } = useTranslation(lng);
  const { data, loading, error } = useApiQuery<SpacesAnswer>('/rag-spaces', {
    componentName: 'KeepDialog',
  });
  const [keeping, setKeeping] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const spaces = data?.spaces.filter(space => space.kind === null) ?? [];

  const keep = async (space: RAGSpace) => {
    if (keeping) return;
    setKeeping(space.id);
    setProblem(null);
    try {
      const [path, body] = keepRequest(what, space.id);
      await apiClient.post(path, body);
      toast.success(t('workbench.assist.keep.done', { space: space.name }));
      onClose();
    } catch (refused: unknown) {
      setProblem(refusalWords(refused, t));
      setKeeping(null);
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-md">
        <ToolDialogHeader>
          <DialogTitle className="break-words pr-8">
            {t('workbench.assist.keep.title', { name: what.name })}
          </DialogTitle>
        </ToolDialogHeader>
        {loading && !data && <Skeleton className="h-24 w-full" />}
        {error !== null && !data && (
          <p role="alert" className="text-sm text-destructive">
            {t('workbench.assist.keep.failed')}
          </p>
        )}
        {data && spaces.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('workbench.assist.keep.none')}</p>
        )}
        {spaces.length > 0 && (
          <ul className="max-h-[50dvh] space-y-1 overflow-y-auto">
            {spaces.map(space => (
              <li key={space.id}>
                <Button
                  variant="ghost"
                  className="min-h-11 w-full justify-start"
                  isLoading={keeping === space.id}
                  aria-disabled={(keeping !== null && keeping !== space.id) || undefined}
                  onClick={() => void keep(space)}
                >
                  <span className="truncate">{space.name}</span>
                </Button>
              </li>
            ))}
          </ul>
        )}
        {problem && (
          <p role="alert" className="text-sm text-destructive">
            {problem}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}

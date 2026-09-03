/**
 * Link / unlink / sync actions of a space's synced sources, with their toasts.
 *
 * Drive folders and Gmail labels (ADR-262) differ by two things only: the
 * i18n namespace and the field that names a source. Everything else — the
 * try/catch, the success and failure wording, the refetch that follows — was
 * duplicated six times in the space page, which is what pushed that component
 * past the complexity ratchet. One hook, called twice.
 */

'use client';

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

export interface SourceActionsConfig<TSource extends { id: string }> {
  /** The sources currently linked — read to name one in a toast. */
  sources: TSource[];
  /** i18n namespace: `spaces.drive` or `spaces.mail`. */
  namespace: string;
  /** How a source names itself for the reader (folder name, label name). */
  nameOf: (source: TSource) => string;
  link: (id: string, name: string) => Promise<unknown>;
  unlink: (id: string, deleteDocuments: boolean) => Promise<unknown>;
  sync: (id: string) => Promise<unknown>;
  /** Reload the space detail after a mutation lands. */
  refetch: () => void;
}

export interface SourceActions {
  handleLink: (id: string, name: string) => Promise<void>;
  handleUnlink: (sourceId: string, deleteDocuments: boolean) => Promise<void>;
  handleSync: (sourceId: string) => Promise<void>;
}

export function useSourceActions<TSource extends { id: string }>({
  sources,
  namespace,
  nameOf,
  link,
  unlink,
  sync,
  refetch,
}: SourceActionsConfig<TSource>): SourceActions {
  const { t } = useTranslation();

  const nameFor = useCallback(
    (sourceId: string) => {
      const source = sources.find(candidate => candidate.id === sourceId);
      return source ? nameOf(source) : '';
    },
    [sources, nameOf]
  );

  const handleLink = useCallback(
    async (id: string, name: string) => {
      try {
        await link(id, name);
        toast.success(t(`${namespace}.link_success`, { name }));
        refetch();
      } catch {
        toast.error(t(`${namespace}.link_error`));
      }
    },
    [link, namespace, refetch, t]
  );

  const handleUnlink = useCallback(
    async (sourceId: string, deleteDocuments: boolean) => {
      const name = nameFor(sourceId);
      try {
        await unlink(sourceId, deleteDocuments);
        toast.success(t(`${namespace}.unlink_success`, { name }));
        refetch();
      } catch {
        toast.error(t(`${namespace}.link_error`));
      }
    },
    [unlink, nameFor, namespace, refetch, t]
  );

  const handleSync = useCallback(
    async (sourceId: string) => {
      const name = nameFor(sourceId);
      try {
        await sync(sourceId);
        toast.success(t(`${namespace}.syncing`));
        refetch();
      } catch {
        toast.error(t(`${namespace}.sync_error`, { name }));
      }
    },
    [sync, nameFor, namespace, refetch, t]
  );

  return { handleLink, handleUnlink, handleSync };
}

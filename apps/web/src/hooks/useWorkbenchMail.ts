'use client';

/**
 * The mail screen's reads and acts on messages (ADR-369, Task 4.7).
 *
 * The folder pane is read once per account (`useApplicationAccountQuery`) and
 * re-read after a label is created, renamed or deleted — the provider decides
 * its name and its place. The open folder is a cursor listing
 * (`useWorkbenchPage`) of the params the screen composes. Every act goes
 * through `useApiMutation`, and none is all-or-nothing (`WorkbenchActOutcome`):
 *
 * - a read state shows AT ONCE; the messages the provider did not do are
 *   rolled back, and a refusal of the whole act rolls back every one (the
 *   error is rethrown so the screen says why); a message whose act is on its
 *   way takes no second one;
 * - a star shows at once the same way;
 * - a move takes exactly the messages it moved out of a place, the others stay
 *   listed; a view (the starred, the sent, all mail) is read again instead, since
 *   what it lists may still answer to it, under a new id;
 * - deleting for good takes exactly the messages it deleted;
 * - a label applied is drawn on its rows, and a row whose label is removed
 *   leaves that label's own listing.
 */
import { useCallback, useRef, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { QueryParamValue } from '@/lib/api-client';
import { isPlace } from '@/lib/workbench/mail';
import type {
  MailFolder,
  MailMoveOutcome,
  MailSummary,
  MailTrashEmptied,
  RereadOptions,
  WorkbenchActOutcome,
} from '@/lib/workbench/types';

const MAIL = '/workbench/mail';
const NO_PARAMS = {};

interface MailFolders {
  folders: MailFolder[];
  truncated?: boolean;
}

export interface WorkbenchMailState {
  /** The pane: system places first, then the person's own; undefined until read. */
  folders: MailFolder[] | undefined;
  /** The mailbox holds more folders than were read (ADR-185: a cut is stated). */
  foldersTruncated: boolean;
  foldersError: unknown;
  messages: WorkbenchPageState<MailSummary>;
  /** Re-reads the listing and the pane. */
  reread: (options?: RereadOptions) => Promise<void>;
  /** Messages whose act is on its way (they take no second one). */
  pending: ReadonlySet<string>;
  setRead: (messages: readonly MailSummary[], read: boolean) => Promise<WorkbenchActOutcome>;
  setStarred: (messages: readonly MailSummary[], starred: boolean) => Promise<WorkbenchActOutcome>;
  /**
   * Sends messages to a place, as the pane names it.
   *
   * @param origin - Where they are, when it is not the listing (a way back).
   */
  move: (ids: readonly string[], to: string, origin?: string) => Promise<MailMoveOutcome>;
  deleteForever: (ids: readonly string[]) => Promise<WorkbenchActOutcome>;
  emptyTrash: () => Promise<MailTrashEmptied | undefined>;
  applyLabels: (
    messages: readonly MailSummary[],
    add: readonly string[],
    remove: readonly string[]
  ) => Promise<void>;
  createLabel: (name: string) => Promise<MailFolder | undefined>;
  /** @returns The folder as it is now: a path changes with its name. */
  renameLabel: (labelId: string, name: string) => Promise<MailFolder | undefined>;
  deleteLabel: (labelId: string) => Promise<void>;
}

/** A row's labels after an application. */
function relabelled(
  row: MailSummary,
  add: readonly string[],
  remove: readonly string[]
): MailSummary {
  const kept = row.label_ids.filter(label => !remove.includes(label));
  return { ...row, label_ids: [...kept, ...add.filter(label => !kept.includes(label))] };
}

/**
 * @param enabled - Whether the tool is ready (nothing is read otherwise).
 * @param folder - The open folder (`system:<role>`, a Gmail label id or a folder name).
 * @param params - The listing's params (`listingParams`), the folder included;
 *   null lists nothing (the drafts have their own listing).
 * @returns The pane, the listing and the acts on messages and labels.
 */
export function useWorkbenchMail(
  enabled: boolean,
  folder: string,
  params: Readonly<Record<string, QueryParamValue>> | null
): WorkbenchMailState {
  const folders = useApplicationAccountQuery<MailFolders>(
    `${MAIL}/folders`,
    'WorkbenchMail',
    enabled
  );
  const messages = useWorkbenchPage<MailSummary>(
    enabled && params ? `${MAIL}/messages` : null,
    params ?? NO_PARAMS
  );
  const { replaceItem, refresh: rereadMessages } = messages;
  const { refetch: rereadFolders } = folders;
  const { mutate: postOutcome } = useApiMutation<Record<string, unknown>, WorkbenchActOutcome>({
    method: 'POST',
    componentName: 'WorkbenchMail',
  });
  const { mutate: postMove } = useApiMutation<Record<string, unknown>, MailMoveOutcome>({
    method: 'POST',
    componentName: 'WorkbenchMail',
  });
  const { mutate: postEmptied } = useApiMutation<Record<string, unknown>, MailTrashEmptied>({
    method: 'POST',
    componentName: 'WorkbenchMail',
  });
  const { mutate: postFolder } = useApiMutation<Record<string, unknown>, MailFolder>({
    method: 'POST',
    componentName: 'WorkbenchMail',
  });
  const { mutate: patchFolder } = useApiMutation<Record<string, unknown>, MailFolder>({
    method: 'PATCH',
    componentName: 'WorkbenchMail',
  });
  const { mutate: remove } = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: 'WorkbenchMail',
  });
  // Set synchronously: a second click lands before the render that shows the first.
  const inFlight = useRef(new Set<string>());
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());

  const settle = useCallback((ids: readonly string[], busy: boolean) => {
    for (const id of ids) {
      if (busy) inFlight.current.add(id);
      else inFlight.current.delete(id);
    }
    setPending(new Set(inFlight.current));
  }, []);

  /** A state shown at once, rolled back for what the provider did not do. */
  const changeRows = useCallback(
    async (
      rows: readonly MailSummary[],
      path: string,
      body: Record<string, unknown>,
      changed: (row: MailSummary) => MailSummary
    ) => {
      const asked = rows.filter(row => !inFlight.current.has(row.id));
      const ids = asked.map(row => row.id);
      if (ids.length === 0) return { done: [], failed: [] };
      settle(ids, true);
      for (const row of asked) replaceItem(row.id, changed(row));
      try {
        const outcome = (await postOutcome(path, { message_ids: ids, ...body })) ?? {
          done: ids,
          failed: [],
        };
        const undone = new Set(outcome.failed.map(failure => failure.id));
        for (const row of asked) if (undone.has(row.id)) replaceItem(row.id, row);
        return outcome;
      } catch (error: unknown) {
        for (const row of asked) replaceItem(row.id, row);
        throw error;
      } finally {
        settle(ids, false);
      }
    },
    [postOutcome, replaceItem, settle]
  );

  const setRead = useCallback(
    (rows: readonly MailSummary[], read: boolean) =>
      changeRows(rows, `${MAIL}/read-state`, { read }, row => ({ ...row, is_read: read })),
    [changeRows]
  );

  const setStarred = useCallback(
    (rows: readonly MailSummary[], starred: boolean) =>
      changeRows(rows, `${MAIL}/star`, { starred }, row => ({ ...row, is_starred: starred })),
    [changeRows]
  );

  const move = useCallback(
    async (ids: readonly string[], to: string, origin: string = folder) => {
      const asked = ids.filter(id => !inFlight.current.has(id));
      if (asked.length === 0) return { done: [], failed: [], moved: [] };
      settle(asked, true);
      try {
        const body = { message_ids: asked, to, origin };
        const outcome = (await postMove(`${MAIL}/move`, body)) ?? {
          done: [],
          failed: [],
          moved: [],
        };
        if (isPlace(folder)) for (const id of outcome.done) replaceItem(id, null);
        else if (outcome.done.length > 0) await rereadMessages();
        return outcome;
      } finally {
        settle(asked, false);
      }
    },
    [folder, postMove, replaceItem, rereadMessages, settle]
  );

  const deleteForever = useCallback(
    async (ids: readonly string[]) => {
      const asked = ids.filter(id => !inFlight.current.has(id));
      if (asked.length === 0) return { done: [], failed: [] };
      settle(asked, true);
      try {
        const body = { message_ids: asked };
        const outcome = (await postOutcome(`${MAIL}/delete-forever`, body)) ?? {
          done: [],
          failed: [],
        };
        for (const id of outcome.done) replaceItem(id, null);
        return outcome;
      } finally {
        settle(asked, false);
      }
    },
    [postOutcome, replaceItem, settle]
  );

  const emptyTrash = useCallback(async () => {
    const emptied = await postEmptied(`${MAIL}/empty-trash`, {});
    await rereadMessages();
    return emptied;
  }, [postEmptied, rereadMessages]);

  const applyLabels = useCallback(
    async (rows: readonly MailSummary[], add: readonly string[], removed: readonly string[]) => {
      await postOutcome(`${MAIL}/labels/apply`, {
        message_ids: rows.map(row => row.id),
        add: [...add],
        remove: [...removed],
      });
      for (const row of rows) {
        replaceItem(row.id, removed.includes(folder) ? null : relabelled(row, add, removed));
      }
    },
    [folder, postOutcome, replaceItem]
  );

  // The act landed; a failed re-read of the pane is the pane's own error, said there.
  const reread = useCallback(() => rereadFolders().catch(() => undefined), [rereadFolders]);

  const createLabel = useCallback(
    async (name: string) => {
      const created = await postFolder(`${MAIL}/labels`, { name });
      await reread();
      return created;
    },
    [postFolder, reread]
  );

  const renameLabel = useCallback(
    async (labelId: string, name: string) => {
      const renamed = await patchFolder(`${MAIL}/labels`, { label_id: labelId, name });
      await reread();
      return renamed;
    },
    [patchFolder, reread]
  );

  const deleteLabel = useCallback(
    async (labelId: string) => {
      await remove(`${MAIL}/labels`, undefined, { params: { label_id: labelId } });
      await reread();
    },
    [remove, reread]
  );

  const rereadScreen = useCallback(
    async (options?: RereadOptions) => {
      await Promise.all([rereadMessages(options), reread()]);
    },
    [rereadMessages, reread]
  );

  return {
    folders: folders.data?.folders,
    foldersTruncated: folders.data?.truncated ?? false,
    foldersError: folders.error,
    messages,
    reread: rereadScreen,
    pending,
    setRead,
    setStarred,
    move,
    deleteForever,
    emptyTrash,
    applyLabels,
    createLabel,
    renameLabel,
    deleteLabel,
  };
}

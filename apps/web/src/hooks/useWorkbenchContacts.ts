'use client';

/**
 * The contacts screen's reads and acts (ADR-369, Task 7.2).
 *
 * The listing is a cursor page (`useWorkbenchPage`) keyed by what it names —
 * the account's contacts, a search, a group, or Google's « other contacts » —
 * so a new search never answers with the previous one, and a search or a
 * group the provider answers in one go says when it may hold more. The groups
 * are read only where the provider has them. An act goes through
 * `useApiMutation`, its error rethrown for the screen to say; a new contact
 * carries its submission's key (a second click creates nothing); a contact
 * gone is a deletion done.
 */
import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { ContactChangeBody, NewContactBody } from '@/lib/workbench/contacts';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type {
  WorkbenchContact,
  WorkbenchContactGroup,
  WorkbenchContactSummary,
} from '@/lib/workbench/types';

const CONTACTS_PATH = '/workbench/contacts';
const NO_PARAMS = {};

/** What the list shows. */
export type ContactsListing =
  | { kind: 'all' }
  | { kind: 'search'; q: string }
  | { kind: 'group'; group: string }
  | { kind: 'other'; q: string };

export interface WorkbenchContactsState {
  list: WorkbenchPageState<WorkbenchContactSummary>;
  groups: WorkbenchItemState<{ groups: WorkbenchContactGroup[] }>;
  create: (body: NewContactBody) => Promise<WorkbenchContact | undefined>;
  update: (body: ContactChangeBody) => Promise<WorkbenchContact | undefined>;
  remove: (id: string) => Promise<void>;
  /** Keeps a contact met in mail among the person's own; its key makes a retry the same act. */
  saveOther: (id: string, idempotencyKey: string) => Promise<WorkbenchContact | undefined>;
  renameGroup: (id: string, name: string) => Promise<void>;
  deleteGroup: (id: string) => Promise<void>;
}

interface OtherContactBody {
  id: string;
  idempotency_key: string;
}

function pathOf(listing: ContactsListing): string | null {
  if (listing.kind !== 'other') return CONTACTS_PATH;
  return listing.q ? `${CONTACTS_PATH}/other` : null;
}

function paramsOfListing(listing: ContactsListing): Record<string, string> {
  if (listing.kind === 'search' || listing.kind === 'other') return { q: listing.q };
  return listing.kind === 'group' ? { group: listing.group } : {};
}

/**
 * @param listing - What the list shows.
 * @param groupsOffered - The provider has groups (the descriptor).
 */
export function useWorkbenchContacts(
  listing: ContactsListing,
  groupsOffered: boolean
): WorkbenchContactsState {
  const params = useMemo(() => paramsOfListing(listing), [listing]);
  const list = useWorkbenchPage<WorkbenchContactSummary>(pathOf(listing), params);
  const groups = useWorkbenchItem<{ groups: WorkbenchContactGroup[] }>(
    groupsOffered ? `${CONTACTS_PATH}/groups` : null,
    NO_PARAMS
  );
  const { refresh } = list;
  const { mutate: post } = useApiMutation<NewContactBody, WorkbenchContact>({
    method: 'POST',
    componentName: 'WorkbenchContacts',
  });
  const { mutate: postOther } = useApiMutation<OtherContactBody, WorkbenchContact>({
    method: 'POST',
    componentName: 'WorkbenchContacts',
  });
  const { mutate: patch } = useApiMutation<ContactChangeBody, WorkbenchContact>({
    method: 'PATCH',
    componentName: 'WorkbenchContacts',
  });
  const { mutate: patchGroup } = useApiMutation<{ id: string; name: string }, void>({
    method: 'PATCH',
    componentName: 'WorkbenchContacts',
  });
  const { mutate: del } = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: 'WorkbenchContacts',
  });

  const create = useCallback(
    async (body: NewContactBody) => {
      const made = await post(CONTACTS_PATH, body);
      await refresh();
      return made;
    },
    [post, refresh]
  );
  const update = useCallback(
    async (body: ContactChangeBody) => {
      const changed = await patch(CONTACTS_PATH, body);
      await refresh();
      return changed;
    },
    [patch, refresh]
  );
  const remove = useCallback(
    async (id: string) => {
      try {
        await del(CONTACTS_PATH, undefined, { params: { id } });
      } catch (error: unknown) {
        if (workbenchRefusal(error)?.key !== 'workbench.errors.item_gone') throw error;
      }
      await refresh();
    },
    [del, refresh]
  );

  const renameGroup = useCallback(
    async (id: string, name: string) => {
      await patchGroup(`${CONTACTS_PATH}/groups`, { id, name });
      await groups.refresh();
    },
    [patchGroup, groups]
  );
  const deleteGroup = useCallback(
    async (id: string) => {
      await del(`${CONTACTS_PATH}/groups`, undefined, { params: { id } });
      await groups.refresh();
    },
    [del, groups]
  );
  const saveOther = useCallback(
    async (id: string, idempotencyKey: string) => {
      const saved = await postOther(`${CONTACTS_PATH}/other/save`, {
        id,
        idempotency_key: idempotencyKey,
      });
      await refresh();
      return saved;
    },
    [postOther, refresh]
  );

  return { list, groups, create, update, remove, saveOther, renameGroup, deleteGroup };
}

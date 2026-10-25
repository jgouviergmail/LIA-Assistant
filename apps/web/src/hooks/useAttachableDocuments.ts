/**
 * The documents the composer may attach: the `ready` documents of every
 * knowledge space of the account, active or not, searched by name. The
 * fetching — keyed by the needle, a late answer dropped — is `useNeedlePage`'s.
 */

'use client';

import { NEEDLE_PAGE_SIZE, useNeedlePage, type NeedlePageState } from '@/hooks/useNeedlePage';
import type { AttachableDocument } from '@/types/rag-spaces';

/** The page the picker asks for — a scroll of fifty names is read at a glance. */
export const ATTACHABLE_PAGE_SIZE = NEEDLE_PAGE_SIZE;

export type AttachableDocumentsState = NeedlePageState<AttachableDocument>;

/**
 * Fetch the attachable documents matching `needle` while `enabled`.
 *
 * @param needle - The name fragment (empty for the whole set).
 * @param enabled - Whether to fetch at all (the dialog is open).
 */
export function useAttachableDocuments(needle: string, enabled: boolean): AttachableDocumentsState {
  return useNeedlePage<AttachableDocument>('/rag-spaces/documents', needle, enabled);
}

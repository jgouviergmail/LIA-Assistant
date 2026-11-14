'use client';

import { useCallback, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import type { User } from '@/lib/auth';
import type { DocumentPreferenceField } from '@/lib/document-preferences';

export interface DocumentPreferencesState {
  /** The field whose choice is being saved, or `null` when nothing is. */
  saving: DocumentPreferenceField | null;
  /** Save one choice; resolves `true` once the profile was re-read with it. */
  save: (field: DocumentPreferenceField, value: string) => Promise<boolean>;
}

/**
 * Saves a document preference through the generic profile update.
 *
 * One save at a time: a choice made while another is on its way is refused
 * by the guard (never by disabling the control that holds the focus), and a
 * failed save leaves the profile — and so the selected option — as it was.
 *
 * @param user - The signed-in account, `null` before it is known.
 * @param refreshUser - Re-reads the profile, so the page shows what was stored.
 * @returns The field being saved and the save action.
 */
export function useDocumentPreferences(
  user: User | null,
  refreshUser: () => Promise<unknown>
): DocumentPreferencesState {
  const [saving, setSaving] = useState<DocumentPreferenceField | null>(null);
  const { mutate } = useApiMutation<Partial<Record<DocumentPreferenceField, string>>, User>({
    method: 'PATCH',
    componentName: 'useDocumentPreferences',
    retainResponse: false,
  });

  const save = useCallback(
    async (field: DocumentPreferenceField, value: string): Promise<boolean> => {
      if (!user || saving !== null || user[field] === value) return false;
      setSaving(field);
      try {
        await mutate(`/users/${user.id}`, { [field]: value });
        await refreshUser();
        return true;
      } catch {
        return false;
      } finally {
        setSaving(null);
      }
    },
    [user, saving, mutate, refreshUser]
  );

  return { saving, save };
}

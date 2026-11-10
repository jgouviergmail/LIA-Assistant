'use client';

/**
 * ContactGroupsField — the groups a contact is in (ADR-369, lot 9).
 *
 * A group is joined by its name, offered from those the account holds; a name nobody holds makes
 * the group, on every provider, because an empty group would exist on one and vanish on another.
 * Each group the contact is in can be left. What a provider keeps for itself is never shown here.
 */
import { X } from '@/lib/icons';
import { useId, useMemo, useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchContactGroup } from '@/lib/workbench/types';

const GROUPS_PATH = '/workbench/contacts/groups';

export interface ContactGroupsFieldProps {
  lng: Language;
  contactId: string;
  /** The account's groups: the names offered. */
  known: readonly WorkbenchContactGroup[];
  /** A contact joined or left: the list of groups reads its counts. */
  onChanged: () => Promise<unknown>;
  nameMax: number | undefined;
}

export function ContactGroupsField({
  lng,
  contactId,
  known,
  onChanged,
  nameMax,
}: ContactGroupsFieldProps) {
  const { t } = useTranslation(lng);
  const names = useId();
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const params = useMemo(() => ({ id: contactId }), [contactId]);
  const member = useWorkbenchItem<{ groups: WorkbenchContactGroup[] }>(
    '/workbench/contacts/member-of',
    params
  );
  const { mutate: post } = useApiMutation<object, unknown>({
    method: 'POST',
    componentName: 'WorkbenchContacts',
  });

  const act = async (run: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true);
    try {
      await run();
      await Promise.all([member.refresh(), onChanged()]);
      return true;
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const join = async (event: FormEvent) => {
    event.preventDefault();
    const name = typed.trim();
    if (!name || busy) return;
    const body = { contact_id: contactId, name };
    if (await act(() => post(`${GROUPS_PATH}/join`, body))) setTyped('');
  };

  return (
    <section aria-label={t('workbench.contacts.groups.title')} className="space-y-2">
      {member.item && member.item.groups.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {member.item.groups.map(group => (
            <li
              key={group.id}
              className="flex items-center gap-1 rounded-full bg-muted py-0.5 pl-2.5 pr-1 text-xs"
            >
              <span className="break-words">{group.name}</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 rounded-full"
                aria-label={t('workbench.contacts.groups.leave')}
                title={t('workbench.contacts.groups.leave')}
                onClick={() =>
                  void act(() =>
                    post(`${GROUPS_PATH}/leave`, { contact_id: contactId, group_id: group.id })
                  )
                }
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={join} className="flex gap-2">
        <Input
          aria-label={t('workbench.contacts.groups.add_label')}
          placeholder={t('workbench.contacts.groups.add_placeholder')}
          list={names}
          value={typed}
          maxLength={nameMax}
          enterKeyHint="done"
          onChange={event => setTyped(event.target.value)}
        />
        <datalist id={names}>
          {known
            .filter(group => group.own)
            .map(group => (
              <option key={group.id} value={group.name}>
                {group.name}
              </option>
            ))}
        </datalist>
        <Button type="submit" variant="outline" size="sm" isLoading={busy}>
          {t('workbench.contacts.groups.add')}
        </Button>
      </form>
    </section>
  );
}

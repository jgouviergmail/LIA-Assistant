'use client';

/**
 * ContactEditor — a new contact, or a change to one (ADR-369, D4).
 *
 * E-mails, phones and addresses are typed lists (`MultiValueField`): a value
 * is added, removed or retyped, never more than the provider holds (its
 * published bound). A change sends only the lists it changed
 * (`lib/workbench/contacts`); a new contact carries ONE key for the life of
 * this form. A refusal is said in its own words — a list the provider cannot
 * hold names its bound. Each opening mounts a new editor. A birthday with no year
 * cannot sit in a date field: it is named beside it, and goes by its button. What LIA
 * found opens filled in, changed from the card as it stands; a new contact can start from
 * a photographed card (ADR-372). Either way the person saves it, or not.
 */
import { Plus, X } from 'lucide-react';
import { useId, useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  CONTACT_KINDS,
  EMPTY_CONTACT,
  birthdayLabel,
  contactChange,
  displayNameOf,
  fieldsOfContact,
  fullBirthday,
  newContactBody,
  valuesMax,
  withCard,
  withFoundValues,
  type ContactChangeBody,
  type ContactFields,
  type ContactList,
  type NewContactBody,
} from '@/lib/workbench/contacts';
import type { ProposedValue } from '@/lib/workbench/assist';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchContact } from '@/lib/workbench/types';
import { generateUUID } from '@/lib/utils';

import { CardAssist } from '../assist/CardAssist';
import { NativeSelect } from '@/components/ui/native-select';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface ContactEditorProps {
  lng: Language;
  /** The contact changed; undefined for a new one. */
  contact: WorkbenchContact | undefined;
  /** What a new contact opens on: another tool's words. */
  prefill?: Partial<ContactFields>;
  /** What the person kept of what LIA found: the form opens with it, unsaved. */
  found?: readonly ProposedValue[];
  bounds: Readonly<Record<string, number>>;
  onCreate: (body: NewContactBody) => Promise<unknown>;
  onUpdate: (body: ContactChangeBody) => Promise<unknown>;
  onClose: () => void;
}

export function ContactEditor({
  lng,
  contact,
  prefill,
  found,
  bounds,
  onCreate,
  onUpdate,
  onClose,
}: ContactEditorProps) {
  const { t } = useTranslation(lng);
  const [initial] = useState(() =>
    contact ? fieldsOfContact(contact) : { ...EMPTY_CONTACT, ...prefill }
  );
  const [fields, setFields] = useState(() => (found ? withFoundValues(initial, found) : initial));
  const [key] = useState(() => generateUUID());
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const busy = useRef(false);
  const set = (change: Partial<ContactFields>) => setFields(current => ({ ...current, ...change }));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (busy.current || !displayNameOf(fields)) return;
    const change = contact ? contactChange(contact.id, initial, fields) : null;
    if (contact && change === null) {
      onClose();
      return;
    }
    busy.current = true;
    setSaving(true);
    setProblem(null);
    try {
      await (change ? onUpdate(change) : onCreate(newContactBody(fields, key)));
      onClose();
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      setProblem(refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed'));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0 sm:max-h-[90dvh] sm:max-w-xl sm:overflow-y-auto">
        <form onSubmit={save} className="space-y-4">
          <ToolDialogHeader>
            <div className="flex items-center gap-1">
              <DialogTitle>
                {t(
                  contact
                    ? 'workbench.contacts.editor.title_edit'
                    : 'workbench.contacts.editor.title_new'
                )}
              </DialogTitle>
              {!contact && (
                <CardAssist
                  lng={lng}
                  maxBytes={bounds.photo_max_bytes}
                  onRead={card => setFields(current => withCard(current, card))}
                />
              )}
            </div>
          </ToolDialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t('workbench.contacts.editor.given_name')}
              value={fields.given_name}
              maxLength={bounds.name_max_chars}
              onChange={event => set({ given_name: event.target.value })}
            />
            <Input
              label={t('workbench.contacts.editor.family_name')}
              value={fields.family_name}
              maxLength={bounds.name_max_chars}
              onChange={event => set({ family_name: event.target.value })}
            />
          </div>
          <Input
            label={t('workbench.contacts.editor.name')}
            value={fields.name}
            maxLength={bounds.name_max_chars}
            onChange={event => set({ name: event.target.value })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t('workbench.contacts.editor.organization')}
              value={fields.organization}
              maxLength={bounds.name_max_chars}
              onChange={event => set({ organization: event.target.value })}
            />
            <Input
              label={t('workbench.contacts.editor.job_title')}
              value={fields.job_title}
              maxLength={bounds.name_max_chars}
              onChange={event => set({ job_title: event.target.value })}
            />
          </div>
          {(['emails', 'phones', 'addresses'] as const).map(list => (
            <MultiValueField
              key={list}
              lng={lng}
              list={list}
              fields={fields}
              max={valuesMax(bounds, list)}
              valueMax={list === 'addresses' ? bounds.address_max_chars : bounds.value_max_chars}
              onChange={set}
            />
          ))}
          <Input
            label={t('workbench.contacts.editor.website')}
            inputMode="url"
            value={fields.website}
            maxLength={bounds.value_max_chars}
            onChange={event => set({ website: event.target.value })}
          />
          <BirthdayField lng={lng} fields={fields} onChange={set} />
          <Textarea
            label={t('workbench.contacts.editor.notes')}
            value={fields.notes}
            rows={3}
            maxLength={bounds.notes_max_chars}
            onChange={event => set({ notes: event.target.value })}
          />
          {problem && (
            <p role="alert" className="text-sm text-destructive">
              {problem}
            </p>
          )}
          <ToolActions>
            <CancelButton lng={lng} onClick={onClose} />
            <Button
              type="submit"
              isLoading={saving}
              aria-disabled={!displayNameOf(fields) || undefined}
            >
              {t(contact ? 'workbench.contacts.editor.save' : 'workbench.contacts.editor.create')}
            </Button>
          </ToolActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** A birthday: a day with its year, or one with none, named and removable. */
function BirthdayField({
  lng,
  fields,
  onChange,
}: {
  lng: Language;
  fields: ContactFields;
  onChange: (change: Partial<ContactFields>) => void;
}) {
  const { t } = useTranslation(lng);
  const held = fields.birthday;
  return (
    <div className="space-y-2">
      <Input
        label={t('workbench.contacts.editor.birthday')}
        type="date"
        value={fullBirthday(held)}
        onChange={event => onChange({ birthday: event.target.value })}
      />
      {held && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            {held.startsWith('--') &&
              t('workbench.contacts.editor.birthday_no_year', { day: birthdayLabel(held, lng) })}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange({ birthday: '' })}
          >
            {t('workbench.contacts.editor.birthday_remove')}
          </Button>
        </div>
      )}
    </div>
  );
}

interface MultiValueFieldProps {
  lng: Language;
  list: ContactList;
  fields: ContactFields;
  max: number;
  valueMax: number | undefined;
  onChange: (change: Partial<ContactFields>) => void;
}

/** One typed list: each value with its kind, added up to the bound, removed at will. */
function MultiValueField({ lng, list, fields, max, valueMax, onChange }: MultiValueFieldProps) {
  const { t } = useTranslation(lng);
  const legend = useId();
  const kinds = CONTACT_KINDS[list];
  const rows =
    list === 'addresses'
      ? fields.addresses.map(item => ({ text: item.formatted, type: item.type }))
      : fields[list].map(item => ({ text: item.value, type: item.type }));
  const write = (next: { text: string; type: string | null }[]) =>
    onChange(
      list === 'addresses'
        ? { addresses: next.map(row => ({ formatted: row.text, type: row.type })) }
        : { [list]: next.map(row => ({ value: row.text, type: row.type })) }
    );
  const at = (index: number, change: Partial<{ text: string; type: string | null }>) =>
    write(rows.map((row, place) => (place === index ? { ...row, ...change } : row)));
  return (
    <fieldset aria-labelledby={legend} className="space-y-2">
      <legend id={legend} className="text-sm font-medium">
        {t(`workbench.contacts.lists.${list}`)}
      </legend>
      {rows.map((row, index) => (
        <div key={index} className="flex items-start gap-2">
          {list === 'addresses' ? (
            // An address keeps its lines (Google writes several): a one-line input
            // would drop them, and the provider would no longer know it unchanged.
            <Textarea
              aria-label={t(`workbench.contacts.lists.${list}_value`, { position: index + 1 })}
              value={row.text}
              rows={2}
              maxLength={valueMax}
              onChange={event => at(index, { text: event.target.value })}
            />
          ) : (
            <Input
              aria-label={t(`workbench.contacts.lists.${list}_value`, { position: index + 1 })}
              value={row.text}
              maxLength={valueMax}
              inputMode={list === 'phones' ? 'tel' : 'email'}
              onChange={event => at(index, { text: event.target.value })}
            />
          )}
          <NativeSelect
            aria-label={t('workbench.contacts.kind_label', { position: index + 1 })}
            value={row.type ?? 'other'}
            onChange={event => at(index, { type: event.target.value })}
            className="w-auto shrink-0 px-2"
          >
            {[...new Set([...kinds, row.type ?? 'other'])].map(kind => (
              <option key={kind} value={kind}>
                {kinds.includes(kind) ? t(`workbench.contacts.kinds.${kind}`) : kind}
              </option>
            ))}
          </NativeSelect>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => write(rows.filter((_, place) => place !== index))}
            aria-label={t('workbench.contacts.remove_value', { position: index + 1 })}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      {rows.length < max ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => write([...rows, { text: '', type: kinds[0] }])}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t(`workbench.contacts.lists.${list}_add`)}
        </Button>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t('workbench.contacts.values_full', { count: max })}
        </p>
      )}
    </fieldset>
  );
}

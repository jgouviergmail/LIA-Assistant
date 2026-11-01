'use client';

/**
 * MailFilters — Gmail's filters, listed and created (ADR-369, Task 4.6/4.7).
 *
 * Each filter reads as what it matches and what it does. A new one matches
 * something (from, to, subject, words, an attachment) and does something (a
 * label, archive, mark read): the form says so before anything is sent, and
 * a submission carries its own key, so a second press creates nothing more. A
 * system label is never offered. Nothing deletes a filter here: Gmail's client
 * has no such act, and the list says where it is done.
 */
import { useId, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import type { MailFilterBody } from '@/hooks/useWorkbenchMailSettings';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailFilter, MailFolder } from '@/lib/workbench/types';

export interface MailFiltersProps {
  lng: Language;
  filters: readonly MailFilter[] | undefined;
  failed: boolean;
  labels: readonly MailFolder[];
  /** The published bound on one criterion. */
  criterionMax: number | undefined;
  /** Resolves true once created (the form starts over), false when refused. */
  onCreate: (body: MailFilterBody) => Promise<boolean>;
}

interface Draft {
  sender: string;
  recipient: string;
  subject: string;
  query: string;
  hasAttachment: boolean;
  labelId: string;
  archive: boolean;
  markRead: boolean;
}

const EMPTY: Draft = {
  sender: '',
  recipient: '',
  subject: '',
  query: '',
  hasAttachment: false,
  labelId: '',
  archive: false,
  markRead: false,
};

/** The filter the form describes, or why it is not one yet. */
function filterOf(draft: Draft): Omit<MailFilterBody, 'idempotency_key'> | 'matches' | 'acts' {
  const criteria = {
    sender: draft.sender.trim() || undefined,
    recipient: draft.recipient.trim() || undefined,
    subject: draft.subject.trim() || undefined,
    query: draft.query.trim() || undefined,
    has_attachment: draft.hasAttachment || undefined,
  };
  if (!Object.values(criteria).some(Boolean)) return 'matches';
  const actions = {
    add_label_id: draft.labelId || undefined,
    archive: draft.archive || undefined,
    mark_read: draft.markRead || undefined,
  };
  if (!Object.values(actions).some(Boolean)) return 'acts';
  return { ...criteria, ...actions };
}

export function MailFilters({
  lng,
  filters,
  failed,
  labels,
  criterionMax,
  onCreate,
}: MailFiltersProps) {
  const { t } = useTranslation(lng);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [problem, setProblem] = useState<'matches' | 'acts' | null>(null);
  const [creating, setCreating] = useState(false);
  const ids = { attachment: useId(), archive: useId(), read: useId(), label: useId() };
  const labelName = (id: string) => labels.find(label => label.id === id)?.name ?? id;

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (creating) return;
    const body = filterOf(draft);
    if (typeof body === 'string') {
      setProblem(body);
      return;
    }
    setProblem(null);
    setCreating(true);
    try {
      if (await onCreate({ ...body, idempotency_key: key })) {
        setDraft(EMPTY);
        setKey(crypto.randomUUID());
      }
    } finally {
      setCreating(false);
    }
  };
  const field = (name: 'sender' | 'recipient' | 'subject' | 'query', labelKey: string) => (
    <Input
      label={t(labelKey)}
      value={draft[name]}
      maxLength={criterionMax}
      onChange={event => setDraft(previous => ({ ...previous, [name]: event.target.value }))}
    />
  );

  return (
    <div className="space-y-5">
      {filters === undefined ? (
        failed ? (
          <EmptyState description={t('workbench.mail.settings.failed')} />
        ) : (
          <Skeleton className="h-24 w-full" />
        )
      ) : filters.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('workbench.mail.filters.none')}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {filters.map(filter => (
            <li key={filter.id} className="space-y-0.5 px-3 py-2 text-sm">
              <p>
                {matchesOf(filter)
                  .map(part => t(part.key, part.values))
                  .join(' · ')}
              </p>
              <p className="text-muted-foreground">
                {actsOf(filter, labelName)
                  .map(part => t(part.key, part.values))
                  .join(' · ')}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{t('workbench.mail.filters.delete_in_gmail')}</p>
      <form onSubmit={create} className="space-y-3 rounded-md border p-3">
        <h3 className="text-sm font-semibold">{t('workbench.mail.filters.new')}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {field('sender', 'workbench.mail.filters.sender')}
          {field('recipient', 'workbench.mail.filters.recipient')}
          {field('subject', 'workbench.mail.filters.subject')}
          {field('query', 'workbench.mail.filters.words')}
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id={ids.attachment}
            checked={draft.hasAttachment}
            onChange={event =>
              setDraft(previous => ({ ...previous, hasAttachment: event.target.checked }))
            }
          />
          <Label htmlFor={ids.attachment}>{t('workbench.mail.filters.has_attachment')}</Label>
        </div>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t('workbench.mail.filters.then')}</legend>
          {labels.length > 0 && (
            <div className="space-y-1.5">
              <Label id={`${ids.label}-label`} htmlFor={ids.label}>
                {t('workbench.mail.filters.add_label')}
              </Label>
              <select
                id={ids.label}
                aria-labelledby={`${ids.label}-label`}
                value={draft.labelId}
                onChange={event =>
                  setDraft(previous => ({ ...previous, labelId: event.target.value }))
                }
                className="h-10 w-full rounded-md border border-input bg-card px-3 text-sm"
              >
                <option value="">{t('workbench.mail.filters.no_label')}</option>
                {labels.map(label => (
                  <option key={label.id} value={label.id}>
                    {label.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Checkbox
              id={ids.archive}
              checked={draft.archive}
              onChange={event =>
                setDraft(previous => ({ ...previous, archive: event.target.checked }))
              }
            />
            <Label htmlFor={ids.archive}>{t('workbench.mail.filters.archive')}</Label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id={ids.read}
              checked={draft.markRead}
              onChange={event =>
                setDraft(previous => ({ ...previous, markRead: event.target.checked }))
              }
            />
            <Label htmlFor={ids.read}>{t('workbench.mail.filters.mark_read')}</Label>
          </div>
        </fieldset>
        {problem && (
          <p role="alert" className="text-sm text-destructive">
            {t(`workbench.mail.filters.needs_${problem}`)}
          </p>
        )}
        <div className="flex justify-end">
          <Button type="submit" isLoading={creating}>
            {t('workbench.mail.filters.create')}
          </Button>
        </div>
      </form>
    </div>
  );
}

/** One part of a filter's summary: a sentence key and the value it quotes. */
interface Part {
  key: string;
  values?: Record<string, string>;
}

const FILTERS = 'workbench.mail.filters';

/** What a filter matches, part by part. */
function matchesOf(filter: MailFilter): Part[] {
  const quoted: [string | null, string][] = [
    [filter.sender, 'from_is'],
    [filter.recipient, 'to_is'],
    [filter.subject, 'subject_has'],
    [filter.query, 'words_are'],
  ];
  const parts: Part[] = quoted.flatMap(([value, key]) =>
    value ? [{ key: `${FILTERS}.${key}`, values: { value } }] : []
  );
  if (filter.has_attachment) parts.push({ key: `${FILTERS}.has_attachment` });
  return parts;
}

/** What a filter does, part by part. */
function actsOf(filter: MailFilter, labelName: (id: string) => string): Part[] {
  const parts: Part[] = filter.add_label_ids.map(id => ({
    key: `${FILTERS}.labels_as`,
    values: { value: labelName(id) },
  }));
  if (filter.archive) parts.push({ key: `${FILTERS}.archives` });
  if (filter.mark_read) parts.push({ key: `${FILTERS}.marks_read` });
  if (filter.forward)
    parts.push({ key: `${FILTERS}.forwards_to`, values: { value: filter.forward } });
  return parts;
}

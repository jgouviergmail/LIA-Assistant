'use client';

/**
 * MailFilters — a mailbox's filters, Gmail's or Outlook's rules, listed, created and
 * deleted (ADR-369).
 *
 * Each filter reads as what it matches and what it does. A new one matches
 * something (from, to, subject, words where Gmail reads them, an attachment) and
 * does something (a label or a folder, archive, mark read): the form says so before
 * anything is sent, and a submission carries its own key, so a second press creates
 * nothing more. A system label is never offered. Deleting one asks first, and says
 * what stays; a rule only Outlook can change offers no deletion, and one whose
 * conditions no field here reads goes by its name.
 */
import { Trash2 } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import type { MailFilterBody } from '@/hooks/useWorkbenchMailSettings';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailFilter, MailFolder } from '@/lib/workbench/types';
import { generateUUID } from '@/lib/utils';

export interface MailFiltersProps {
  lng: Language;
  filters: readonly MailFilter[] | undefined;
  /** Why the list could not be read, in the reader's words. */
  failure: string | null;
  labels: readonly MailFolder[];
  /** The mailbox reads a search of its own. */
  wordsOffered: boolean;
  /** A filter moves to a folder here, where Gmail applies a label. */
  folders: boolean;
  /** The published bound on one criterion. */
  criterionMax: number | undefined;
  /** Resolves true once created (the form starts over), false when refused. */
  onCreate: (body: MailFilterBody) => Promise<boolean>;
  /** Deletes one; says its own refusal. */
  onDelete: (filter: MailFilter) => Promise<void>;
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
  failure,
  labels,
  wordsOffered,
  folders,
  criterionMax,
  onCreate,
  onDelete,
}: MailFiltersProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [key, setKey] = useState(() => generateUUID());
  const [problem, setProblem] = useState<'matches' | 'acts' | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
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
        setKey(generateUUID());
      }
    } finally {
      setCreating(false);
    }
  };
  const said = (parts: readonly Part[]) => parts.map(part => t(part.key, part.values)).join(' · ');
  const remove = async (filter: MailFilter) => {
    if (deleting) return;
    // Two filters on one sender differ only by what they do: the question says both.
    const facts = [said(matchesOf(filter)), said(actsOf(filter, labelName, folders))];
    const confirmed = await confirm({
      title: t('workbench.mail.filters.delete_title'),
      description: [...facts, '', t('workbench.mail.filters.delete_description')].join('\n'),
      confirmLabel: t('common.delete'),
    });
    if (!confirmed) return;
    setDeleting(filter.id);
    try {
      await onDelete(filter);
    } finally {
      setDeleting(null);
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
        failure ? (
          <EmptyState description={failure} />
        ) : (
          <Skeleton className="h-24 w-full" />
        )
      ) : filters.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('workbench.mail.filters.none')}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {filters.map(filter => (
            <li key={filter.id} className="flex items-start gap-2 px-3 py-2 text-sm">
              <div className="min-w-0 flex-1 space-y-0.5 break-words">
                <p>{said(matchesOf(filter))}</p>
                <p className="text-muted-foreground">{said(actsOf(filter, labelName, folders))}</p>
              </div>
              {!filter.read_only && (
                <RowActions
                  menuLabel={t('workbench.mail.filters.row_actions', {
                    value: said(matchesOf(filter)),
                  })}
                  actions={[
                    {
                      key: 'delete',
                      label: t('workbench.mail.filters.delete', {
                        value: said(matchesOf(filter)),
                      }),
                      icon: Trash2,
                      tone: 'destructive',
                      loading: deleting === filter.id,
                      onSelect: () => void remove(filter),
                    },
                  ]}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={create} className="space-y-3 rounded-md border p-3">
        <h3 className="text-sm font-semibold">{t('workbench.mail.filters.new')}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {field('sender', 'workbench.mail.filters.sender')}
          {field('recipient', 'workbench.mail.filters.recipient')}
          {field('subject', 'workbench.mail.filters.subject')}
          {wordsOffered && field('query', 'workbench.mail.filters.words')}
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
                {t(`workbench.mail.filters.${folders ? 'move_to' : 'add_label'}`)}
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
                <option value="">
                  {t(`workbench.mail.filters.${folders ? 'no_folder' : 'no_label'}`)}
                </option>
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
      {confirmDialog}
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
  if (parts.length === 0 && filter.name) {
    parts.push({ key: `${FILTERS}.named`, values: { value: filter.name } });
  }
  return parts;
}

/** What a filter does, part by part. */
function actsOf(filter: MailFilter, labelName: (id: string) => string, folders: boolean): Part[] {
  const parts: Part[] = filter.add_label_ids.map(id => ({
    key: `${FILTERS}.${folders ? 'moves_to' : 'labels_as'}`,
    values: { value: labelName(id) },
  }));
  if (filter.archive) parts.push({ key: `${FILTERS}.archives` });
  if (filter.mark_read) parts.push({ key: `${FILTERS}.marks_read` });
  if (filter.forward)
    parts.push({ key: `${FILTERS}.forwards_to`, values: { value: filter.forward } });
  return parts;
}

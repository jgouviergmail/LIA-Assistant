/**
 * The « + »'s pickers: something the person already holds joins the message as a COPY.
 *
 * One dialog for every source — the knowledge-space documents (ADR-295), the
 * kept answers and the generated files (2026-10-24): it searches the source by
 * name, states a cut page against its exact total, bounds the selection by
 * the room left in the message, and turns each pick into an attachment through
 * the source's copy endpoint. A pick the API refuses is told by its reason;
 * the others still land. Each source brings its words, its rows and its copy.
 */

'use client';

import { useCallback, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, type LucideIcon } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchInput } from '@/components/ui/search-input';
import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import type { NeedlePageState } from '@/hooks/useNeedlePage';
import { getApiErrorCode } from '@/lib/api-error';
import { attachmentMeta, type AttachmentCreated } from '@/lib/attach-sources';

/** The i18n KEYS a source names its dialog with. */
export interface PickerWords {
  title: string;
  description: string;
  searchPlaceholder: string;
  loading: string;
  empty: string;
  emptySearch: string;
  error: string;
  moreHint: string;
  remaining: string;
  attach: string;
  alreadyAttached: string;
  attachError: string;
}

export interface AttachSourcePickerDialogProps<T> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Attachments the message can still take (the per-message cap minus the strip). */
  remaining: number;
  /** Hand a created attachment to the composer's strip. */
  onAttached: (meta: ServerAttachmentMeta) => AddServerAttachmentOutcome;
  icon: LucideIcon;
  itemIcon: LucideIcon;
  words: PickerWords;
  needle: string;
  onNeedleChange: (needle: string) => void;
  page: NeedlePageState<T>;
  idOf: (item: T) => string;
  labelOf: (item: T) => string;
  metaOf: (item: T) => ReactNode;
  /** The name the strip shows; the created copy's own when absent. */
  nameOf?: (item: T) => string;
  copy: (item: T) => Promise<AttachmentCreated>;
  /** The refusals the copy endpoint names, as i18n keys. */
  refusals?: Readonly<Record<string, string>>;
  /** Controls above the search (a gallery's family). */
  toolbar?: ReactNode;
}

function PickerRows<T>({
  props,
  selected,
  full,
  attaching,
  onToggle,
}: {
  props: AttachSourcePickerDialogProps<T>;
  selected: T[];
  full: boolean;
  attaching: boolean;
  onToggle: (item: T) => void;
}) {
  const { t } = useTranslation();
  const { page, needle, words, idOf, labelOf, metaOf, itemIcon: ItemIcon } = props;
  if (page.loading && page.items.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">{t(words.loading)}</span>
      </div>
    );
  }
  if (page.error) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-destructive">
        <p>{t(words.error)}</p>
      </div>
    );
  }
  if (page.items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-sm text-muted-foreground">
        <ItemIcon className="h-8 w-8 mb-2" aria-hidden="true" />
        <p>{t(needle ? words.emptySearch : words.empty)}</p>
      </div>
    );
  }
  return (
    <ul className="divide-y">
      {page.items.map(item => {
        const id = idOf(item);
        const checked = selected.some(pick => idOf(pick) === id);
        const inputId = `attach-source-${id}`;
        return (
          <li key={id}>
            <label
              htmlFor={inputId}
              className="flex items-center gap-3 px-3 py-2.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
            >
              <Checkbox
                id={inputId}
                checked={checked}
                disabled={!checked && (full || attaching)}
                onChange={() => onToggle(item)}
              />
              <ItemIcon className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{labelOf(item)}</span>
                <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  {metaOf(item)}
                </span>
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

export function AttachSourcePickerDialog<T>(props: AttachSourcePickerDialogProps<T>) {
  const { open, onOpenChange, remaining, onAttached, words, page, idOf, onNeedleChange } = props;
  const { t } = useTranslation();
  const [selected, setSelected] = useState<T[]>([]);
  const [attaching, setAttaching] = useState(false);
  const full = selected.length >= remaining;
  const Icon = props.icon;

  const toggle = (item: T) => {
    const id = idOf(item);
    setSelected(previous =>
      previous.some(pick => idOf(pick) === id)
        ? previous.filter(pick => idOf(pick) !== id)
        : [...previous, item]
    );
  };

  const close = useCallback(
    (isOpen: boolean) => {
      if (!isOpen) {
        setSelected([]);
        onNeedleChange('');
      }
      onOpenChange(isOpen);
    },
    [onOpenChange, onNeedleChange]
  );

  const attach = async () => {
    setAttaching(true);
    let attached = 0;
    for (const item of selected) {
      try {
        const created = await props.copy(item);
        const outcome = onAttached(attachmentMeta(created, props.nameOf?.(item)));
        if ('error' in outcome) {
          toast.error(
            outcome.error === 'max_attachments'
              ? t('chat.attachments.max_attachments', { max: outcome.max })
              : t(words.alreadyAttached)
          );
          break;
        }
        attached += 1;
      } catch (err) {
        const code = getApiErrorCode(err);
        const key = code ? props.refusals?.[code] : undefined;
        toast.error(t(key ?? words.attachError, { name: props.labelOf(item) }));
      }
    }
    setAttaching(false);
    if (attached > 0) close(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
            {t(words.title)}
          </DialogTitle>
          <DialogDescription>{t(words.description)}</DialogDescription>
        </DialogHeader>

        {props.toolbar}
        <SearchInput
          placeholder={t(words.searchPlaceholder)}
          aria-label={t(words.searchPlaceholder)}
          onSearchChange={onNeedleChange}
          loading={page.loading}
        />

        <div className="min-h-[200px] max-h-[320px] overflow-y-auto rounded-md border">
          <PickerRows
            props={props}
            selected={selected}
            full={full}
            attaching={attaching}
            onToggle={toggle}
          />
        </div>

        {page.total > page.items.length && (
          <p className="text-xs text-muted-foreground">
            {t(words.moreHint, { shown: page.items.length, total: page.total })}
          </p>
        )}
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {t(words.remaining, { count: remaining - selected.length })}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={attaching}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void attach()} disabled={selected.length === 0 || attaching}>
            {attaching && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {t(words.attach, { count: selected.length })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

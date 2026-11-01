'use client';

/**
 * AttachablePicker — the person's own files a new message may carry (ADR-369,
 * spec §13: what they uploaded and what LIA produced for them, still live).
 *
 * One page at a time with its EXACT total (ADR-185), a search by name, and the
 * two bounds the send refuses beyond — how many files, how many bytes in all
 * (`attachments_max`, `attachments_max_bytes`, ADR-184): a file that would
 * pass one is said so, never silently dropped. Nothing is uploaded here.
 */
import { Check, Paperclip, Search } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { fileSize } from '@/lib/workbench/mail';
import type { AttachableFile, AttachablePage } from '@/lib/workbench/types';

export interface AttachablePickerProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chosen: readonly AttachableFile[];
  maxFiles: number;
  maxBytes: number;
  onToggle: (file: AttachableFile) => void;
}

export function AttachablePicker({
  lng,
  open,
  onOpenChange,
  chosen,
  maxFiles,
  maxBytes,
  onToggle,
}: AttachablePickerProps) {
  const { t } = useTranslation(lng);
  const [words, setWords] = useState('');
  // The offsets of the pages walked through: « Previous » goes back to the one before.
  const [query, setQuery] = useState<{ q: string; trail: number[] }>({ q: '', trail: [0] });
  const offset = query.trail.at(-1) ?? 0;
  const fieldId = useId();
  const page = useWorkbenchItem<AttachablePage>(open ? '/workbench/mail/attachable' : null, {
    q: query.q || undefined,
    offset,
  });
  const chosenIds = new Set(chosen.map(file => file.id));
  const chosenBytes = chosen.reduce((sum, file) => sum + file.size, 0);

  const search = (event: FormEvent) => {
    event.preventDefault();
    setQuery({ q: words.trim(), trail: [0] });
  };
  const refusal = (file: AttachableFile): string | null => {
    if (chosenIds.has(file.id)) return null;
    if (chosen.length >= maxFiles) return t('workbench.mail.files.max_files', { count: maxFiles });
    if (chosenBytes + file.size > maxBytes) {
      return t('workbench.mail.files.max_bytes', { max: fileSize(maxBytes, lng) });
    }
    return null;
  };
  const items = page.item?.items ?? [];
  const shownTo = offset + items.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('workbench.mail.files.title')}</DialogTitle>
          <DialogDescription>
            {t('workbench.mail.files.description', {
              count: maxFiles,
              max: fileSize(maxBytes, lng),
            })}
          </DialogDescription>
        </DialogHeader>
        <form role="search" onSubmit={search} className="flex items-center gap-2">
          <Label htmlFor={fieldId} className="sr-only">
            {t('workbench.mail.files.search_label')}
          </Label>
          <Input
            id={fieldId}
            type="search"
            value={words}
            onChange={event => setWords(event.target.value)}
            placeholder={t('workbench.mail.files.search_placeholder')}
            className="flex-1"
          />
          <Button
            type="submit"
            variant="outline"
            size="icon"
            aria-label={t('workbench.mail.search')}
          >
            <Search className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
        {page.loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map(index => (
              <Skeleton key={index} className="h-11 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={Paperclip}
            description={t(
              page.error ? 'workbench.mail.files.failed' : 'workbench.mail.files.empty'
            )}
          />
        ) : (
          <ul className="max-h-80 divide-y overflow-y-auto rounded-md border">
            {items.map(file => {
              const held = refusal(file);
              const picked = chosenIds.has(file.id);
              return (
                <li key={file.id} className="flex items-center gap-3 px-3 py-2">
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-sm font-medium">{file.filename}</span>
                    <span className="text-xs text-muted-foreground">
                      {held ?? fileSize(file.size, lng)}
                    </span>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant={picked ? 'default' : 'outline'}
                    aria-pressed={picked}
                    aria-disabled={held !== null || undefined}
                    onClick={() => {
                      if (held === null) onToggle(file);
                    }}
                    aria-label={t('workbench.mail.files.attach_named', { name: file.filename })}
                    className="gap-1.5"
                  >
                    {picked && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
                    {t(picked ? 'workbench.mail.files.attached' : 'workbench.mail.files.attach')}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        {page.item && page.item.total > 0 && (
          <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
            <span>
              {t('workbench.mail.files.range', {
                from: offset + 1,
                to: shownTo,
                total: page.item.total,
              })}
            </span>
            <span className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                aria-disabled={query.trail.length < 2 || undefined}
                onClick={() => {
                  if (query.trail.length > 1) {
                    setQuery(previous => ({ ...previous, trail: previous.trail.slice(0, -1) }));
                  }
                }}
              >
                {t('workbench.mail.files.previous')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                aria-disabled={page.item.next_offset === null || undefined}
                onClick={() => {
                  const next = page.item?.next_offset;
                  if (typeof next === 'number') {
                    setQuery(previous => ({ ...previous, trail: [...previous.trail, next] }));
                  }
                }}
              >
                {t('workbench.mail.files.next')}
              </Button>
            </span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

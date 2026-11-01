'use client';

/**
 * MailSearchBar — the person's words and the three chips (ADR-369, spec §6.3).
 *
 * The words are searched when the person presses Enter (or the search
 * button), never on every key: each search is a read of the provider, counted
 * in the account's read window. The box takes the Gmail-style syntax and is
 * bounded by the very length the listing refuses beyond (`search_max_chars`,
 * ADR-184). The chips narrow what is listed: unread, with an attachment (only
 * where the provider can filter on it — the descriptor says), and a period of
 * the account's days (the last one included).
 */
import { CalendarRange, ChevronDown, Paperclip, Search, X } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { MailPeriod, MailSearch } from '@/lib/workbench/mail';
import { formatDay } from '@/lib/workbench/tasks';

const PRESETS: readonly Exclude<MailPeriod, 'custom'>[] = ['any', 'week', 'month', 'year'];

const CHIP =
  'h-9 rounded-full px-3 aria-pressed:border-primary/40 aria-pressed:bg-primary/10 aria-pressed:text-primary';

export interface MailSearchBarProps {
  lng: Language;
  search: MailSearch;
  onChange: (next: MailSearch) => void;
  /** The provider filters on attachments (the descriptor's `attachment_filter`). */
  attachmentsOffered: boolean;
  /** The listing's published bound on the words. */
  maxChars: number | undefined;
}

export function MailSearchBar({
  lng,
  search,
  onChange,
  attachmentsOffered,
  maxChars,
}: MailSearchBarProps) {
  const { t } = useTranslation(lng);
  const [words, setWords] = useState(search.q);
  const [rangeOpen, setRangeOpen] = useState(false);
  const fieldId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onChange({ ...search, q: words });
  };
  const clear = () => {
    setWords('');
    if (search.q) onChange({ ...search, q: '' });
  };
  const periodLabel =
    search.period === 'custom'
      ? t('workbench.mail.period.custom_label', {
          from: search.from ? formatDay(search.from, lng) : '…',
          to: search.to ? formatDay(search.to, lng) : '…',
        })
      : t(`workbench.mail.period.${search.period}`);

  return (
    <div className="space-y-2.5 border-b px-4 py-3">
      <form role="search" onSubmit={submit} className="flex items-center gap-2">
        <Label htmlFor={fieldId} className="sr-only">
          {t('workbench.mail.search_label')}
        </Label>
        <div className="relative min-w-0 flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id={fieldId}
            type="search"
            value={words}
            maxLength={maxChars}
            onChange={event => setWords(event.target.value)}
            placeholder={t('workbench.mail.search_placeholder')}
            className="pl-9"
            enterKeyHint="search"
          />
        </div>
        {words && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={clear}
            aria-label={t('workbench.mail.search_clear')}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        )}
        <Button type="submit" variant="outline" size="icon" aria-label={t('workbench.mail.search')}>
          <Search className="h-4 w-4" aria-hidden="true" />
        </Button>
      </form>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-pressed={search.unread}
          onClick={() => onChange({ ...search, unread: !search.unread })}
          className={CHIP}
        >
          {t('workbench.mail.chip_unread')}
        </Button>
        {attachmentsOffered && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-pressed={search.attachments}
            onClick={() => onChange({ ...search, attachments: !search.attachments })}
            className={cn(CHIP, 'gap-1.5')}
          >
            <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
            {t('workbench.mail.chip_attachments')}
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-pressed={search.period !== 'any'}
              className={cn(CHIP, 'gap-1.5')}
              aria-label={t('workbench.mail.period.chip', { period: periodLabel })}
            >
              <CalendarRange className="h-3.5 w-3.5" aria-hidden="true" />
              {search.period === 'any' ? t('workbench.mail.period.title') : periodLabel}
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuRadioGroup
              value={search.period === 'custom' ? '' : search.period}
              onValueChange={value => {
                const preset = PRESETS.find(item => item === value);
                if (preset) onChange({ ...search, period: preset, from: '', to: '' });
              }}
            >
              {PRESETS.map(preset => (
                <DropdownMenuRadioItem key={preset} value={preset}>
                  {t(`workbench.mail.period.${preset}`)}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setRangeOpen(true)}>
              {t('workbench.mail.period.choose')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <PeriodDialog
        // Each opening starts from the period on screen, not from the last draft.
        key={rangeOpen ? 'open' : 'closed'}
        lng={lng}
        open={rangeOpen}
        onOpenChange={setRangeOpen}
        initial={search}
        onApply={(from, to) => onChange({ ...search, period: 'custom', from, to })}
      />
    </div>
  );
}

interface PeriodDialogProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: MailSearch;
  onApply: (from: string, to: string) => void;
}

/** Two native day fields: the first and the last day, both included, either open. */
function PeriodDialog({ lng, open, onOpenChange, initial, onApply }: PeriodDialogProps) {
  const { t } = useTranslation(lng);
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const fromId = useId();
  const toId = useId();
  const reversed = from !== '' && to !== '' && to < from;
  const empty = from === '' && to === '';

  const apply = (event: FormEvent) => {
    event.preventDefault();
    if (reversed || empty) return;
    onApply(from, to);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={apply} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t('workbench.mail.period.dialog_title')}</DialogTitle>
            <DialogDescription>{t('workbench.mail.period.dialog_description')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label id={`${fromId}-label`} htmlFor={fromId}>
                {t('workbench.mail.period.from')}
              </Label>
              <Input
                id={fromId}
                aria-labelledby={`${fromId}-label`}
                type="date"
                value={from}
                onChange={event => setFrom(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label id={`${toId}-label`} htmlFor={toId}>
                {t('workbench.mail.period.to')}
              </Label>
              <Input
                id={toId}
                aria-labelledby={`${toId}-label`}
                type="date"
                value={to}
                min={from || undefined}
                onChange={event => setTo(event.target.value)}
                error={reversed ? t('workbench.mail.period.reversed') : undefined}
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" aria-disabled={reversed || empty}>
              {t('workbench.mail.period.apply')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

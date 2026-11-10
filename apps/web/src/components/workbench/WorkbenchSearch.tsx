'use client';

/**
 * WorkbenchSearch — one search across the tools (ADR-369, lot 13).
 *
 * Ctrl+K (Cmd+K) or its button opens it, wherever the person stands in the section. The chord is
 * no single key, so the switch of the tools' shortcuts leaves it on (WCAG 2.1.4). A search reads
 * four providers: it starts on Enter, never while the person types. Each tool that answered is
 * drawn under its name: a tool with nothing says so, a cut is said, and so is a mailbox searched
 * from its inbox alone; a tool that failed is named (ADR-292). A hit opens in its tool and closes
 * the dialog; the words and the answer wait for the person to come back. What is a question rather
 * than words to find goes to LIA from the same line, unsent (`useAskLia`).
 */
import { Search } from '@/lib/icons';
import Link from 'next/link';
import { useEffect, useEffectEvent, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { datedDay } from '@/lib/workbench/calendar/format';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { hitHref, searchOffered, toolHref } from '@/lib/workbench/search';
import { toolSpec, WORKBENCH_HEADER_ICON } from '@/lib/workbench/tools';
import type {
  GlobalSearch,
  SearchableTool,
  SearchHit,
  ToolHits,
  WorkbenchAvailability,
} from '@/lib/workbench/types';

import { AssistStars } from '@/components/selection-assist/AssistStars';
import { useAskLia } from './assist/useAskLia';
import { ToolDialogHeader } from './ToolForm';

const SEARCH_PATH = '/workbench/search';
const CHORD_LABEL = 'Ctrl/⌘ K';
const LINK_CLASS =
  'block rounded-md px-2 py-2 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

function isSearchChord(event: KeyboardEvent): boolean {
  return (
    (event.ctrlKey || event.metaKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === 'k'
  );
}

/** Whether the chord belongs to what the person is writing, or to a dialog already open. */
function leftAlone(event: KeyboardEvent): boolean {
  if (event.defaultPrevented) return true;
  const target = event.target;
  return (
    target instanceof HTMLElement &&
    target.closest('[contenteditable="true"],[role="dialog"],[role="alertdialog"]') !== null
  );
}

function useSearchChord(enabled: boolean, open: () => void): void {
  const opened = useEffectEvent(open);
  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isSearchChord(event) || leftAlone(event)) return;
      event.preventDefault();
      opened();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}

export interface WorkbenchSearchProps {
  lng: Language;
  availability: WorkbenchAvailability;
}

export function WorkbenchSearch({ lng, availability }: WorkbenchSearchProps) {
  const { t } = useTranslation(lng);
  const offered = searchOffered(availability);
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const askLia = useAskLia(lng);
  const found = useWorkbenchItem<GlobalSearch>(asked ? SEARCH_PATH : null, {
    q: asked ?? undefined,
  });
  useSearchChord(offered, () => setOpen(true));
  if (!offered) return null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const words = typed.trim();
    if (!words) return;
    if (words === asked) void found.refresh();
    else setAsked(words);
  };
  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className={WORKBENCH_HEADER_ICON}
        aria-label={t('workbench.search.open')}
        aria-keyshortcuts="Control+K Meta+K"
        title={`${t('workbench.search.open')} (${CHORD_LABEL})`}
        onClick={() => setOpen(true)}
      >
        <Search className="h-4 w-4" aria-hidden="true" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[85dvh] flex-col sm:max-w-xl">
          <ToolDialogHeader>
            <DialogTitle>{t('workbench.search.title')}</DialogTitle>
            <DialogDescription>{t('workbench.search.description')}</DialogDescription>
          </ToolDialogHeader>
          <form role="search" className="flex gap-2" onSubmit={submit}>
            <Input
              type="search"
              aria-label={t('workbench.search.label')}
              placeholder={t('workbench.search.label')}
              value={typed}
              maxLength={availability.limits.search_max_chars}
              enterKeyHint="search"
              onChange={event => setTyped(event.target.value)}
            />
            <Button type="submit">{t('workbench.search.go')}</Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0"
              aria-label={t('workbench.ask.label')}
              aria-disabled={!typed.trim() || undefined}
              title={t('workbench.ask.label')}
              onClick={() => {
                if (typed.trim()) askLia(typed.trim());
              }}
            >
              <AssistStars className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>
          {asked && <SearchAnswer lng={lng} found={found} onOpen={() => setOpen(false)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

interface AnswerProps {
  lng: Language;
  found: WorkbenchItemState<GlobalSearch>;
  onOpen: () => void;
}

function SearchAnswer({ lng, found, onOpen }: AnswerProps) {
  const { t } = useTranslation(lng);
  if (found.loading) {
    return (
      <div className="space-y-2" aria-busy="true">
        {[1, 2, 3].map(index => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  const answer = found.item;
  if (!answer) {
    const refusal = workbenchRefusal(found.error);
    return (
      <EmptyState
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.search.unavailable')}
        action={{ label: t('workbench.states.retry'), onClick: () => void found.refresh() }}
      />
    );
  }
  const silent = answer.results.length === 0 && answer.failed.length === 0;
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
      <p className="sr-only" aria-live="polite">
        {t('workbench.search.done')}
      </p>
      {answer.failed.length > 0 && <FailedTools lng={lng} tools={answer.failed} />}
      {silent && <EmptyState description={t('workbench.search.nowhere')} />}
      {answer.results.map(group => (
        <ToolGroup key={group.tool} lng={lng} group={group} onOpen={onOpen} />
      ))}
    </div>
  );
}

function FailedTools({ lng, tools }: { lng: Language; tools: readonly SearchableTool[] }) {
  const { t } = useTranslation(lng);
  const names = new Intl.ListFormat(getIntlLocale(lng), { type: 'conjunction' }).format(
    tools.map(tool => t(toolSpec(tool).labelKey))
  );
  return (
    <p role="status" className="text-sm text-destructive">
      {t('workbench.search.failed')} {names}
    </p>
  );
}

function ToolGroup({ lng, group, onOpen }: { lng: Language; group: ToolHits; onOpen: () => void }) {
  const { t } = useTranslation(lng);
  const { icon: Icon, labelKey } = toolSpec(group.tool);
  const name = t(labelKey);
  return (
    <section aria-label={name} className="min-w-0 text-sm">
      <h3 className="flex items-center gap-2 font-semibold">
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {name}
      </h3>
      {group.inbox_only && (
        <p className="text-xs text-muted-foreground">{t('workbench.search.inbox_only')}</p>
      )}
      {group.hits.length === 0 ? (
        <p className="px-2 py-1 text-muted-foreground">{t('workbench.search.none_here')}</p>
      ) : (
        <ul className="divide-y">
          {group.hits.map(hit => (
            <li key={`${hit.calendar_id ?? ''}:${hit.id}`}>
              <HitLink lng={lng} tool={group.tool} hit={hit} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
      {group.truncated && (
        <Link
          href={toolHref(group.tool, lng)}
          onClick={onOpen}
          className={`${LINK_CLASS} text-xs text-primary`}
        >
          {t('workbench.search.more', { tool: name })}
        </Link>
      )}
    </section>
  );
}

function HitLink({
  lng,
  tool,
  hit,
  onOpen,
}: {
  lng: Language;
  tool: SearchableTool;
  hit: SearchHit;
  onOpen: () => void;
}) {
  const { t } = useTranslation(lng);
  const line = [hit.day && datedDay(hit.day, lng), hit.subtitle].filter(Boolean).join(' · ');
  return (
    <Link href={hitHref(tool, hit, lng)} onClick={onOpen} className={LINK_CLASS}>
      <span className="block truncate font-medium text-foreground">
        {hit.title || t('workbench.search.untitled')}
      </span>
      {line && <span className="block truncate text-xs text-muted-foreground">{line}</span>}
    </Link>
  );
}

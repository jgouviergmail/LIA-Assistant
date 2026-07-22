'use client';

/**
 * ChatSearchBar — sub-header surface of the chat history search (QW-2).
 *
 * Rendered under the chat header (in the line the totals banner used to
 * occupy). Composed from four focused pieces, each with its own small render
 * path (CC discipline):
 * - `MobileSearchRow`: the input row toggled from the header icon (< 880px —
 *   the desktop input lives in the header itself);
 * - `HistoryBanner`: amber "you are viewing the past" bar with the way back;
 * - `StatusRow`: "N results in loaded messages" + the server-search
 *   affordance;
 * - `ResultsPanel`: dated, keyset-paginated whole-history results.
 *
 * Excerpts are rendered as React segments (`prefix`/`<mark>`/`suffix`) built
 * by `buildSearchExcerpt` — no HTML injection anywhere.
 */

import { useEffect, useRef } from 'react';
import { History, Loader2, Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ConversationMessage } from '@/hooks/useConversation';
import { buildSearchExcerpt } from '@/lib/search-excerpt';
import { getIntlLocale, type Language } from '@/i18n/settings';

export interface ChatSearchBarProps {
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  loadedMatchCount: number;
  serverSearchAvailable: boolean;
  panelOpen: boolean;
  serverResults: ConversationMessage[];
  serverHasMore: boolean;
  serverLoading: boolean;
  serverError: boolean;
  /** Term the open results were fetched with (drives the excerpt marks). */
  excerptTerm: string;
  historyView: boolean;
  /** Disables result jumps (e.g. while a stream is active). */
  jumpDisabled: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onRunServerSearch: () => void;
  onLoadMoreServerResults: () => void;
  onClosePanel: () => void;
  onJump: (row: ConversationMessage) => void;
  onReturnToPresent: () => void;
}

function ResultRow({
  row,
  excerptTerm,
  disabled,
  locale,
  onJump,
}: {
  row: ConversationMessage;
  excerptTerm: string;
  disabled: boolean;
  locale: string;
  onJump: (row: ConversationMessage) => void;
}) {
  const { t } = useTranslation();
  const dateLabel = new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(row.created_at));
  const excerpt = buildSearchExcerpt(row.content, excerptTerm);

  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onJump(row)}
        aria-label={t('chat.search.jump_aria', { date: dateLabel })}
        className="w-full text-left px-3 py-2 rounded-md hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span className="block text-[11px] font-semibold text-muted-foreground">{dateLabel}</span>
        <span className="block text-xs text-foreground/90 truncate">
          {excerpt ? (
            <>
              {excerpt.prefix}
              <mark className="lia-search-mark">{excerpt.match}</mark>
              {excerpt.suffix}
            </>
          ) : (
            row.content.replace(/<[^>]*>/g, ' ').slice(0, 120)
          )}
        </span>
      </button>
    </li>
  );
}

function MobileSearchRow(props: ChatSearchBarProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the input when the overlay opens (the header toggle regains focus
  // naturally when the row unmounts).
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <div className="flex mobile:hidden items-center gap-2 px-3 py-2">
      <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-hidden />
      <input
        ref={inputRef}
        type="search"
        value={props.searchQuery}
        onChange={e => props.setSearchQuery(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Escape') props.onCloseMobile();
        }}
        placeholder={t('conversations.search_placeholder')}
        aria-label={t('conversations.search_placeholder')}
        className="flex-1 h-8 px-2 text-xs rounded-full bg-background border border-border focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <button
        type="button"
        onClick={props.onCloseMobile}
        aria-label={t('chat.search.close_mobile')}
        className="p-1.5 rounded-full hover:bg-muted"
      >
        <X className="h-3.5 w-3.5 text-muted-foreground" />
      </button>
    </div>
  );
}

function HistoryBanner({ onReturnToPresent }: { onReturnToPresent: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center gap-3 px-3 py-2 bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200">
      <History className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>{t('chat.search.history_view')}</span>
      <button
        type="button"
        onClick={onReturnToPresent}
        className="font-semibold underline decoration-amber-500 hover:decoration-amber-700 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {t('chat.search.back_to_present')}
      </button>
    </div>
  );
}

function StatusRow(props: ChatSearchBarProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center gap-4 px-3 py-1.5">
      <span role="status" className="text-muted-foreground">
        {t('chat.search.loaded_count', { count: props.loadedMatchCount })}
      </span>
      {props.serverSearchAvailable && (
        <button
          type="button"
          onClick={props.panelOpen ? props.onClosePanel : props.onRunServerSearch}
          aria-expanded={props.panelOpen}
          className="font-semibold text-primary hover:text-primary/80 underline decoration-primary/40 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t('chat.search.search_all')}
        </button>
      )}
    </div>
  );
}

/** Status line of the panel header — exactly one of four states. */
function panelStatusKey(props: ChatSearchBarProps): string {
  if (props.serverLoading && props.serverResults.length === 0) return 'chat.search.searching';
  if (props.serverError) return 'chat.search.remote_error';
  if (props.serverResults.length === 0) return 'chat.search.remote_none';
  return 'chat.search.remote_count';
}

function ResultsPanel(props: ChatSearchBarProps) {
  const { t, i18n } = useTranslation();
  const locale = getIntlLocale(i18n.language as Language);

  return (
    <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-40 w-[min(38rem,92vw)] rounded-lg border border-border bg-popover text-popover-foreground shadow-lg">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/60">
        <span role="status" className="text-muted-foreground">
          {t(panelStatusKey(props), { count: props.serverResults.length })}
        </span>
        <button
          type="button"
          onClick={props.onClosePanel}
          aria-label={t('chat.search.close_panel')}
          className="p-1 rounded-full hover:bg-muted"
        >
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>
      <ul className="max-h-72 overflow-y-auto p-1 space-y-0.5" role="list">
        {props.serverResults.map(row => (
          <ResultRow
            key={row.id}
            row={row}
            excerptTerm={props.excerptTerm}
            disabled={props.jumpDisabled}
            locale={locale}
            onJump={props.onJump}
          />
        ))}
      </ul>
      {(props.serverHasMore || props.serverLoading) && (
        <div className="px-3 py-2 border-t border-border/60 text-center">
          {props.serverLoading ? (
            <Loader2 className="h-4 w-4 animate-spin inline text-muted-foreground" aria-hidden />
          ) : (
            <button
              type="button"
              onClick={props.onLoadMoreServerResults}
              className="font-semibold text-primary hover:text-primary/80 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {t('chat.search.load_more')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatSearchBar(props: ChatSearchBarProps) {
  const showStatusRow = !props.historyView && props.searchQuery.trim().length > 0;

  if (!props.mobileOpen && !showStatusRow && !props.historyView) return null;

  return (
    <div className="relative border-b border-border/40 bg-card/80 text-xs">
      {props.mobileOpen && <MobileSearchRow {...props} />}
      {props.historyView && <HistoryBanner onReturnToPresent={props.onReturnToPresent} />}
      {showStatusRow && <StatusRow {...props} />}
      {props.panelOpen && <ResultsPanel {...props} />}
    </div>
  );
}

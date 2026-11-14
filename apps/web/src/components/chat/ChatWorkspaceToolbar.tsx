'use client';

import type { ComponentProps, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { leavingCancelsTurn } from '@/lib/discussion-leave';
import { Search, WifiOff, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { VoiceModeBadge } from '@/components/voice/VoiceModeBadge';
import { ActiveSpacesIndicator } from '@/components/spaces/ActiveSpacesIndicator';
import { ChatContextUsage } from './ChatContextUsage';
import { ConversationSwitcher, type ConversationSwitcherProps } from './ConversationSwitcher';

interface ToolbarSearch {
  value: string;
  onChange: (value: string) => void;
  mobileOpen: boolean;
  toggleMobile: () => void;
}

function ChatHeaderSearch({ value, onChange, mobileOpen, toggleMobile }: ToolbarSearch) {
  const { t } = useTranslation();
  return (
    <>
      <button
        type="button"
        onClick={toggleMobile}
        aria-expanded={mobileOpen}
        aria-label={t('chat.search.open_mobile')}
        data-eyes-anchor-start
        className="mobile:hidden min-h-10 min-w-10 rounded-full p-2 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Search className="mx-auto h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </button>
      <div className="relative hidden min-w-0 items-center mobile:flex" data-eyes-anchor-start>
        <Search
          className="pointer-events-none absolute left-2 h-3.5 w-3.5 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          data-chat-search
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={t('conversations.search_placeholder')}
          aria-label={t('conversations.search_placeholder')}
          className="h-8 w-48 max-w-full rounded-full border bg-background pl-7 pr-7 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange('')}
            aria-label={t('conversations.search_clear')}
            className="absolute right-1 rounded-full p-0.5 hover:bg-muted"
          >
            <X className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
          </button>
        )}
      </div>
    </>
  );
}

interface ChatWorkspaceToolbarProps {
  apiAvailable: boolean;
  search: ToolbarSearch;
  switcher?: ConversationSwitcherProps;
  typing: boolean;
  voice: ComponentProps<typeof VoiceModeBadge>;
  context: ComponentProps<typeof ChatContextUsage>;
  resetControl: ReactNode;
}

/**
 * The discussion's header: ONE row on a phone (owner, 2026-11-11).
 *
 * Read left to right: search, hands-free, discussions, context, knowledge
 * spaces, then the reset — which keeps the RIGHT edge at every width. Three
 * layouts, all decided by the CONTAINER's width so the same controls fit the
 * full page and the World panel:
 *
 * - from 19rem — a phone — everything sits on one row: the five controls
 *   centred in what the reset leaves (two equal auto margins), and the
 *   discussion's title the ONE thing that gives way: it truncates, its
 *   control keeps its icon and its accessible name;
 * - from 35rem the search takes the left, the reset the right and the centre
 *   group the middle;
 * - under 19rem (a 320 px screen, or a small phone with the text enlarged) no
 *   row holds six controls: the search keeps a line and the centre group
 *   wraps, which is the net that keeps every control on screen. The bounds are
 *   in rem on purpose — they follow the interface text size.
 */
export function ChatWorkspaceToolbar({
  apiAvailable,
  search,
  switcher,
  typing,
  voice,
  context,
  resetControl,
}: ChatWorkspaceToolbarProps) {
  const { t } = useTranslation();
  const blocked = leavingCancelsTurn(typing, switcher?.rules);
  return (
    <div className="@container relative border-b bg-card/60 px-2 py-2 shadow-sm backdrop-blur-xl sm:px-6 sm:py-4">
      <div
        className={cn(
          'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-1',
          '@min-[19rem]:flex',
          '@min-[35rem]:grid @min-[35rem]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] @min-[35rem]:gap-2'
        )}
      >
        <div className="col-span-2 flex min-w-0 items-center gap-1 @min-[19rem]:ml-auto @min-[19rem]:shrink-0 @min-[35rem]:col-span-1 @min-[35rem]:ml-0 @min-[35rem]:shrink @min-[35rem]:gap-2">
          {!apiAvailable && (
            // With no room for its words the pill keeps its sign: the words
            // stay the accessible name (`lib/mobile-visibility.ts`).
            <div className="flex min-w-0 items-center gap-1.5 text-xs font-semibold text-destructive @min-[640px]:rounded-full @min-[640px]:border @min-[640px]:border-destructive/25 @min-[640px]:bg-destructive/10 @min-[640px]:px-2 @min-[640px]:py-1.5">
              <WifiOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="sr-only @min-[640px]:not-sr-only @min-[640px]:min-w-0 @min-[640px]:truncate">
                {t('chat.input.status.offline')}
              </span>
            </div>
          )}
          <ChatHeaderSearch {...search} />
        </div>
        <div
          className="flex min-w-0 flex-wrap items-center justify-center gap-1 @min-[19rem]:flex-nowrap @min-[35rem]:gap-2"
          data-eyes-anchor-end
        >
          <VoiceModeBadge {...voice} />
          {switcher && (
            <ConversationSwitcher
              {...switcher}
              blockedReason={blocked ? t('chat.discussions.inline_busy') : undefined}
            />
          )}
          <ChatContextUsage {...context} />
          <ActiveSpacesIndicator />
        </div>
        <div className="flex shrink-0 items-center justify-end @min-[19rem]:ml-auto @min-[35rem]:ml-0 @min-[35rem]:min-w-0 @min-[35rem]:shrink">
          {resetControl}
        </div>
      </div>
    </div>
  );
}

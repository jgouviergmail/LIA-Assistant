'use client';

/**
 * SlashCommandMenu — hand-built WAI-ARIA combobox popup for the chat input
 * (UXR Lot 8, A4; arbitration 2a: no cmdk dependency).
 *
 * The textarea stays the focused input; this listbox floats above it. All
 * state and key handling live in `useSlashMenu` (module-level hook — CC
 * discipline): ↑/↓ wrap, Enter selects, Escape closes keeping the text,
 * Tab closes, IME composition ignored, zero matches auto-closes. Option
 * clicks use onMouseDown+preventDefault so they land before the blur.
 */

import { useCallback, useMemo, useState } from 'react';
import { CornerDownLeft, TerminalSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  filterSlashCommands,
  isSlashTrigger,
  type SlashCommand,
} from '@/lib/slash-commands';

export interface UseSlashMenuArgs {
  message: string;
  commands?: readonly SlashCommand[];
  onSelect: (command: SlashCommand) => void;
}

const NO_COMMANDS: readonly SlashCommand[] = [];

export interface UseSlashMenuReturn {
  open: boolean;
  items: SlashCommand[];
  activeIndex: number;
  /** True when the key was consumed by the menu (caller must return). */
  handleKeyDown: (event: React.KeyboardEvent) => boolean;
  select: (command: SlashCommand) => void;
  listboxId: string;
  activeOptionId: string | undefined;
}

const LISTBOX_ID = 'slash-command-listbox';

export function useSlashMenu({
  message,
  commands = NO_COMMANDS,
  onSelect,
}: UseSlashMenuArgs): UseSlashMenuReturn {
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const items = useMemo(
    () => (isSlashTrigger(message) ? filterSlashCommands(commands, message) : []),
    [message, commands]
  );
  // Render-phase adjustment of own state (official React pattern — never a
  // setState in an effect): every keystroke re-filters the list, so the
  // highlight returns to the FIRST option instead of landing on an
  // arbitrary clamped position of the new list (review finding).
  const [filterFor, setFilterFor] = useState(message);
  if (message !== filterFor) {
    setFilterFor(message);
    setActiveIndex(0);
  }
  // Zero matches auto-closes (Enter then sends normally); Escape dismisses
  // until the value changes.
  const open = items.length > 0 && dismissedFor !== message;
  const boundedIndex = Math.min(activeIndex, Math.max(0, items.length - 1));

  const select = useCallback(
    (command: SlashCommand) => {
      setDismissedFor(null);
      setActiveIndex(0);
      onSelect(command);
    },
    [onSelect]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent): boolean => {
      if (!open || event.nativeEvent.isComposing) return false;
      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          setActiveIndex((boundedIndex + 1) % items.length);
          return true;
        case 'ArrowUp':
          event.preventDefault();
          setActiveIndex((boundedIndex - 1 + items.length) % items.length);
          return true;
        case 'Enter':
          event.preventDefault();
          select(items[boundedIndex]);
          return true;
        case 'Escape':
          event.preventDefault();
          setDismissedFor(message);
          return true;
        case 'Tab':
          setDismissedFor(message);
          return false; // let focus move
        default:
          return false;
      }
    },
    [open, items, boundedIndex, message, select]
  );

  return {
    open,
    items,
    activeIndex: boundedIndex,
    handleKeyDown,
    select,
    listboxId: LISTBOX_ID,
    activeOptionId: open ? `slash-option-${boundedIndex}` : undefined,
  };
}

export function SlashCommandMenu({
  menu,
}: {
  menu: Pick<UseSlashMenuReturn, 'open' | 'items' | 'activeIndex' | 'select' | 'listboxId'>;
}) {
  const { t } = useTranslation();
  if (!menu.open) return null;
  return (
    <div className="absolute bottom-full left-0 right-0 z-20 mb-2 overflow-hidden rounded-lg border border-border/60 bg-popover shadow-lg">
      <ul
        id={menu.listboxId}
        role="listbox"
        aria-label={t('chat.slash.aria')}
        className="max-h-64 overflow-y-auto py-1"
      >
        {menu.items.map((command, index) => (
          <li
            key={command.id}
            id={`slash-option-${index}`}
            role="option"
            aria-selected={index === menu.activeIndex}
            onMouseDown={event => {
              // Land before the textarea blur.
              event.preventDefault();
              menu.select(command);
            }}
            className={`flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${
              index === menu.activeIndex ? 'bg-primary/10 text-foreground' : 'text-foreground/90'
            }`}
          >
            {command.kind === 'local' ? (
              <TerminalSquare className="h-3.5 w-3.5 shrink-0 text-primary/70" aria-hidden />
            ) : (
              <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            )}
            <span className="font-medium">/{command.id}</span>
            <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
              {command.description}
            </span>
            <span className="shrink-0 rounded border border-border/40 px-1 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              {t(command.kind === 'local' ? 'chat.slash.kind_local' : 'chat.slash.kind_chat')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

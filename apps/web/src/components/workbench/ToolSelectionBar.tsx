'use client';

/**
 * ToolSelectionBar — what a selection can become, on one line (ADR-369 amendment 2026-11-11).
 *
 * A tool says what it offers (`SelectionAct`), in the order it reads, and the bar decides how it is
 * drawn, as a detail's bar does (`DetailBar`): the count and the way out, the acts used most as
 * icons (`quick`), the rest behind « … », and the deletion last, solid red (ADR-207). The bar is
 * MEASURED, not ruled by a breakpoint: drawn whole while it fits, and where the room runs out the
 * quick acts join the list instead of taking a line; they come back with the room. A « … » of one
 * is never opened: its act stands in the bar. An act that must be told where (a label, another
 * list) lists its places under its own line, or under its icon where it stands in the bar. While
 * `held` nothing runs and every control keeps the focus; what holds them is said under the bar.
 */
import { Loader2, MoreHorizontal, type LucideIcon } from '@/lib/icons';
import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SelectionBar, type SelectionBarProps } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

import { BarAct } from './DetailBar';

/** One thing a selection can become, wherever the bar draws it. */
export interface SelectionAct {
  /** Names the act among its bar's, and tells the bar when what it offers changed. */
  id: string;
  /** What the ear is told, what a pointer reads, and the word of the list. */
  label: string;
  icon: LucideIcon;
  /** What it does; left out for an act that lists its places. */
  onSelect?: () => void;
  /** The places it can go, as lines of a menu: it runs nothing itself, and they hold themselves. */
  lines?: ReactNode;
  /** Used most: it stands in the bar while the bar holds it. */
  quick?: boolean;
  /** It deletes: solid red, the bar's last act, never in the list. */
  danger?: boolean;
  /** Its answer is on the way. */
  busy?: boolean;
}

export interface ToolSelectionBarProps extends Pick<
  SelectionBarProps,
  | 'regionLabel'
  | 'countLabel'
  | 'selectAllLabel'
  | 'clearLabel'
  | 'pageState'
  | 'onSelectAll'
  | 'onClear'
> {
  lng: Language;
  /** What the selection can become, in the order it reads. */
  acts: readonly SelectionAct[];
  /** Nothing runs for now: an act is on its way, or the selection is past its bound. */
  held?: boolean;
  /** What holds the acts back, said under the bar. */
  note?: string;
}

/**
 * Whether the bar folds, measured on the bar itself.
 *
 * Drawn whole it overflows (nothing in a compact bar shrinks), and what the whole took is
 * remembered so the icons come back once the room does. What the bar draws changing voids what
 * was remembered: it is drawn whole and measured again, before it is painted.
 *
 * @param signature - What the bar draws: its count and its acts.
 * @returns The bar's ref, and whether its quick acts join the list.
 */
function useFold(signature: string): { barRef: RefObject<HTMLDivElement | null>; folded: boolean } {
  const barRef = useRef<HTMLDivElement>(null);
  const [room, setRoom] = useState(0);
  const [whole, setWhole] = useState<{ of: string; width: number } | null>(null);
  const folded = whole !== null && whole.of === signature && room < whole.width;

  // The room follows the bar: a pane dragged, a window resized, a message opened beside the list.
  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const observer = new ResizeObserver(() => setRoom(bar.clientWidth));
    observer.observe(bar);
    return () => observer.disconnect();
  }, []);

  // Drawn whole and past its room: what the whole takes is kept, which folds it before the paint.
  // Read again whenever the room or what is drawn changes.
  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!bar || folded || bar.scrollWidth <= bar.clientWidth) return;
    setRoom(bar.clientWidth);
    setWhole({ of: signature, width: bar.scrollWidth });
  }, [folded, signature, room]);

  return { barRef, folded };
}

/** How wide a list of places grows: a long name of a label or of a list takes lines, not the screen. */
const PLACES_WIDTH = 'max-w-72';

/** An icon that opens a list: « … », or the places of an act that stands in the bar. */
function ListIcon({
  label,
  icon: Icon,
  busy,
  className,
  children,
}: {
  label: string;
  icon: LucideIcon;
  busy: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={label}
          aria-busy={busy || undefined}
          title={label}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Icon className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className={className}>
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** One act as the bar draws it: its icon, or the icon that lists its places. */
function IconAct({ act, held }: { act: SelectionAct; held: boolean }) {
  const { label, icon, onSelect, busy = false } = act;
  if (act.lines) {
    return (
      <ListIcon label={label} icon={icon} busy={busy} className={PLACES_WIDTH}>
        {act.lines}
      </ListIcon>
    );
  }
  return <BarAct act={{ label, icon, onSelect, busy, held }} />;
}

/** One act as the list draws it: its line, or the line that opens its places. */
function LineAct({ act, held }: { act: SelectionAct; held: boolean }) {
  const { label, icon: Icon } = act;
  if (act.lines) {
    return (
      <DropdownMenuSub>
        <DropdownMenuSubTrigger disabled={held}>
          <Icon className="h-4 w-4" aria-hidden="true" />
          {label}
        </DropdownMenuSubTrigger>
        <DropdownMenuPortal>
          <DropdownMenuSubContent className={PLACES_WIDTH}>{act.lines}</DropdownMenuSubContent>
        </DropdownMenuPortal>
      </DropdownMenuSub>
    );
  }
  return (
    <DropdownMenuItem disabled={held} onSelect={act.onSelect}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </DropdownMenuItem>
  );
}

/** The deletion: solid red at the size of its neighbours (ADR-207). */
function DangerAct({ act, held }: { act: SelectionAct; held: boolean }) {
  const { label, icon: Icon } = act;
  return (
    <Button
      type="button"
      variant="destructive"
      size="icon"
      isLoading={act.busy}
      // A guard, not the attribute: `aria-disabled` keeps the focus where it is.
      aria-disabled={held || undefined}
      aria-label={label}
      title={label}
      onClick={() => {
        if (!held) act.onSelect?.();
      }}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}

export function ToolSelectionBar({
  lng,
  acts,
  held = false,
  note,
  ...frame
}: ToolSelectionBarProps) {
  const { t } = useTranslation(lng);
  const { barRef, folded } = useFold([frame.countLabel, ...acts.map(act => act.id)].join('\n'));
  const waiting = acts.filter(act => !act.danger && (folded || !act.quick));
  // A « … » of one is never opened: its act stands in the bar.
  const listed = waiting.length > 1 ? waiting : [];
  const standing = acts.filter(act => !act.danger && !listed.includes(act));
  return (
    <div className="border-b px-3 py-2">
      {/* Whole, the bar keeps its line so that it can be measured; folded, it may take another. */}
      <SelectionBar
        compact
        barRef={barRef}
        className={folded ? undefined : 'flex-nowrap'}
        {...frame}
      >
        {standing.map(act => (
          <IconAct key={act.id} act={act} held={held} />
        ))}
        {listed.length > 0 && (
          <ListIcon
            label={t('common.more_actions')}
            icon={MoreHorizontal}
            busy={listed.some(act => act.busy)}
          >
            {listed.map(act => (
              <LineAct key={act.id} act={act} held={held} />
            ))}
          </ListIcon>
        )}
        {acts
          .filter(act => act.danger)
          .map(act => (
            <DangerAct key={act.id} act={act} held={held} />
          ))}
      </SelectionBar>
      {note && (
        <p role="status" className="px-1 pt-2 text-sm text-destructive">
          {note}
        </p>
      )}
    </div>
  );
}

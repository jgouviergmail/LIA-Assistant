'use client';

/**
 * DetailBar — the bar of a detail (ADR-369, owner 2026-11-06).
 *
 * The way out, then what can be done, as a message's reader draws it: icons at the end of the bar,
 * at every width, what is less common behind « … », and every bar ends on the same two acts: the
 * deletion, then the question to LIA. A tool says what it offers (`DetailAct`), in any order, the
 * bar decides how it is drawn, so a « … » of one is never opened: its act stands in the bar. An act
 * that must be told where opens its own list under its icon, even for one place: an icon names
 * nothing on a phone, and a press never goes somewhere the person has not read. Where the room
 * runs out, larger text on a small phone, the tool's name gives way, then the icons take another
 * line: an act is never cut. What LIA can do on the thing stands under that same last icon: a
 * screen with little room gains no control, and the list says the rest (owner, 2026-11-06).
 */
import { Loader2, MessageCircle, MoreHorizontal, type LucideIcon } from 'lucide-react';
import { Fragment, type Ref } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';

import { AssistStars } from './assist/AssistStars';
import { DetailClose } from './DetailClose';

/** One press, wherever it is drawn: in the bar, behind « … », or on a line of an act's list. */
export interface DetailDeed {
  /** What the ear is told, what a pointer reads, and the word of the menu. */
  label: string;
  icon: LucideIcon;
  /** What it does; left out for a link, or for what submits a form. */
  onSelect?: () => void;
  /** The address it follows. */
  href?: string;
  /** That address leaves for a tab that cannot reach back. */
  external?: boolean;
  /** The form it submits, from outside it. */
  form?: string;
  /** It deletes: the bar ends on it. */
  danger?: boolean;
  /** It takes the thing to LIA: the bar's last act (`askAct`). */
  asks?: boolean;
  /** Its answer is on the way. */
  busy?: boolean;
  /** Held back for now: it keeps the focus and runs nothing. */
  held?: boolean;
  /** On a list, it starts a group of its own. */
  ruled?: boolean;
}

/** An act that must be told where: its icon lists the places, it runs nothing itself. */
interface DetailChoice {
  label: string;
  icon: LucideIcon;
  /** Where it can go. */
  choices: readonly DetailDeed[];
  /** It stands in the bar: a list behind « … » would answer nothing. */
  more?: undefined;
  danger?: undefined;
  /** It takes the thing to LIA: the bar's last act (`askAct`). */
  asks?: boolean;
  /** One of its lines is on its way: it still opens. */
  busy?: boolean;
  /** It stands in a field's label line: it takes no more height than the words there. */
  compact?: boolean;
}

export type DetailAct =
  | (DetailDeed & {
      /** Less common: it waits behind « … ». */
      more?: boolean;
      choices?: undefined;
    })
  | DetailChoice;

/** An act that exists on a condition, for the list a tool declares. */
export function actIf(condition: boolean, act: DetailAct): readonly DetailAct[] {
  return condition ? [act] : [];
}

/** What LIA can do on the thing open, under the question's own icon. */
export interface AssistOffer {
  lines: readonly DetailDeed[];
  /** One of the lines is on its way. */
  busy?: boolean;
}

const NOTHING_OFFERED: AssistOffer = { lines: [] };

/**
 * The question to LIA, the same in every tool, and what LIA can do here under the same icon.
 *
 * @param label - What the icon and the question are called.
 * @param onSelect - Takes the thing to the chat.
 * @param assist - What else it offers; nothing, and the icon is the question itself. A last line
 *   that also goes to the chat (`asks`) keeps the question in its group.
 * @returns The bar's last act.
 */
export function askAct(
  label: string,
  onSelect: () => void,
  { lines, busy = false }: AssistOffer = NOTHING_OFFERED
): DetailAct {
  if (lines.length === 0) return { label, icon: AssistStars, asks: true, onSelect };
  const question = { label, icon: MessageCircle, ruled: !lines.at(-1)?.asks, onSelect };
  return { label, icon: AssistStars, asks: true, busy, choices: [...lines, question] };
}

function linkOf(act: DetailDeed) {
  return {
    href: act.href,
    ...(act.external ? { target: '_blank', rel: 'noopener noreferrer' } : {}),
  };
}

/** One act as the bar draws it, for a bar of a tool's own (the message's reader). */
export function BarAct({ act }: { act: DetailAct }) {
  const { icon: Icon, label } = act;
  if (act.choices) {
    return (
      <ListAct
        label={label}
        icon={Icon}
        lines={act.choices}
        busy={act.busy}
        compact={act.compact}
        asks={act.asks}
      />
    );
  }
  const tone = act.danger ? 'text-destructive hover:text-destructive' : undefined;
  if (act.href) {
    return (
      <Button asChild variant="ghost" size="icon" className={tone}>
        <a {...linkOf(act)} aria-label={label} title={label}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </a>
      </Button>
    );
  }
  return (
    <Button
      type={act.form ? 'submit' : 'button'}
      form={act.form}
      variant="ghost"
      size="icon"
      className={tone}
      isLoading={act.busy}
      aria-disabled={act.held || undefined}
      aria-label={label}
      title={label}
      onClick={() => {
        if (!act.held) act.onSelect?.();
      }}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}

function MenuAct({ act }: { act: DetailDeed }) {
  const { icon: Icon, label } = act;
  const tone = act.danger ? 'text-destructive' : undefined;
  if (act.href) {
    return (
      <DropdownMenuItem asChild className={tone}>
        <a {...linkOf(act)}>
          <Icon className="h-4 w-4" aria-hidden="true" />
          {label}
        </a>
      </DropdownMenuItem>
    );
  }
  return (
    <DropdownMenuItem className={tone} disabled={act.held} onSelect={act.onSelect}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </DropdownMenuItem>
  );
}

/** An icon that opens a list: « … », or the places an act can go. */
function ListAct({
  label,
  icon: Icon,
  lines,
  busy = false,
  compact = false,
  asks = false,
}: {
  label: string;
  icon: LucideIcon;
  lines: readonly DetailDeed[];
  busy?: boolean;
  compact?: boolean;
  /** What LIA can do stands here: its answer gives the focus back to this icon. */
  asks?: boolean;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          // In a label's line the star itself ends on the field's edge, its padding hanging out.
          className={compact ? '-my-2 -mr-2 h-8 w-8' : undefined}
          aria-label={label}
          aria-busy={busy || undefined}
          title={label}
          data-assist-trigger={asks || undefined}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Icon className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {lines.map((line, index) => (
          <Fragment key={`${line.label}:${index}`}>
            {line.ruled && index > 0 && <DropdownMenuSeparator />}
            <MenuAct act={line} />
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export interface DetailBarProps {
  lng: Language;
  /** What the cross is called. */
  closeLabel: string;
  /** Where it goes back to: the tool's name. */
  backLabel: string;
  onClose: () => void;
  closeRef?: Ref<HTMLButtonElement>;
  /** What can be done, in the order it reads; none while the thing is being read. */
  acts?: readonly DetailAct[];
}

export function DetailBar({
  lng,
  closeLabel,
  backLabel,
  onClose,
  closeRef,
  acts = [],
}: DetailBarProps) {
  const { t } = useTranslation(lng);
  const waiting = acts.filter(act => act.more);
  const menu = waiting.length > 1 ? waiting : [];
  const shown = acts.filter(act => !menu.includes(act));
  const ending = [...shown.filter(act => act.danger), ...shown.filter(act => act.asks)];
  const leading = shown.filter(act => !ending.includes(act));
  return (
    <div data-testid="detail-bar" className={cn('flex items-center gap-1 border-b px-2 py-1.5')}>
      <DetailClose
        closeLabel={closeLabel}
        backLabel={backLabel}
        onClose={onClose}
        buttonRef={closeRef}
      />
      {acts.length > 0 && (
        <span
          data-testid="detail-acts"
          className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-0.5"
        >
          {leading.map((act, index) => (
            <BarAct key={`${act.label}:${index}`} act={act} />
          ))}
          {menu.length > 0 && (
            <ListAct label={t('common.more_actions')} icon={MoreHorizontal} lines={menu} />
          )}
          {ending.map((act, index) => (
            <BarAct key={`${act.label}:${index}`} act={act} />
          ))}
        </span>
      )}
    </div>
  );
}

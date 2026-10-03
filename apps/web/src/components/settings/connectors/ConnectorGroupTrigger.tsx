/**
 * ConnectorGroupTrigger — the ONE visual grammar of a collapsed connector
 * group (K01).
 *
 * Before K01 the 14 accordion triggers had four dialects: a green check for
 * connected groups, a destructive-red row for error groups, a naked label for
 * available OAuth groups, domain emojis or a key icon elsewhere. Collapsed —
 * which is how the section always opens — the connected/disconnected
 * distinction relied on remembering which dialect meant what.
 *
 * The grammar is now fixed: `[group icon] [label] (count) … [state chip]`.
 *
 * The leading slot names WHICH group this is (a provider's brand mark, a
 * domain icon in the theme colour) — fourteen identical state icons in a
 * column told the reader nothing they could not read in the chip. The STATE
 * lives in the chip, in WORDS and with its own small icon: color alone would
 * exclude color-blind users and screen readers alike (the accessible name of
 * the trigger includes the chip text). An error group keeps a destructive
 * leading icon, since its identity IS the problem.
 */

import type { ComponentType } from 'react';
import { CheckCircle2, AlertTriangle, Plug } from 'lucide-react';

import { cn } from '@/lib/utils';

export type ConnectorGroupState = 'connected' | 'error' | 'available';

const STATE_ICON: Record<ConnectorGroupState, typeof CheckCircle2> = {
  connected: CheckCircle2,
  error: AlertTriangle,
  available: Plug,
};

const STATE_CHIP_TONE: Record<ConnectorGroupState, string> = {
  connected: 'bg-success/10 text-success border-success/30',
  error: 'bg-destructive/10 text-destructive border-destructive/30',
  available: 'bg-muted text-muted-foreground border-border/60',
};

const STATE_CHIP_KEY: Record<ConnectorGroupState, string> = {
  connected: 'settings.connectors.group_state.connected',
  error: 'settings.connectors.group_state.attention',
  available: 'settings.connectors.group_state.available',
};

export interface ConnectorGroupTriggerProps {
  state: ConnectorGroupState;
  /** Already-localized group label. */
  label: string;
  /** Number of services in the group (shown muted, as before K01). */
  count: number;
  /**
   * The group's identity: a lucide icon or a brand mark. Decorative
   * (`aria-hidden`) — the label names the group. Painted in the theme colour,
   * or destructive for an error group; a multicolour brand mark keeps its own.
   */
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  t: (key: string) => string;
}

/** Row content rendered INSIDE an `<AccordionTrigger>` (which owns the chevron). */
export function ConnectorGroupTrigger({
  state,
  label,
  count,
  icon: GroupIcon,
  t,
}: ConnectorGroupTriggerProps) {
  const StateIcon = STATE_ICON[state];
  return (
    <span className="flex flex-1 items-center gap-2 min-w-0 pr-2">
      <GroupIcon
        className={cn('h-4 w-4 shrink-0', state === 'error' ? 'text-destructive' : 'text-primary')}
        aria-hidden="true"
      />
      <span className="truncate">{label}</span>
      <span className="text-muted-foreground text-sm shrink-0">({count})</span>
      <span
        className={cn(
          'ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-px-11 font-medium',
          STATE_CHIP_TONE[state]
        )}
      >
        <StateIcon className="h-3 w-3 shrink-0" aria-hidden="true" />
        {/* Below `sm` the word is for assistive technology only: on a phone the
            chip's width truncated the group's own name (« Services Goo… »),
            and the state stays visible through the icon's SHAPE (check, alert,
            plug), never through colour alone. */}
        <span className="sr-only sm:not-sr-only">{t(STATE_CHIP_KEY[state])}</span>
      </span>
    </span>
  );
}

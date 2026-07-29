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
 * The grammar is now fixed: `[state icon] [glyph?] [label] (count) … [state chip]`.
 * The chip states the group state IN WORDS: color alone would exclude
 * color-blind users and screen readers alike (the accessible name of the
 * trigger includes the chip text).
 */

import { CheckCircle2, AlertTriangle, Plug } from 'lucide-react';

import { cn } from '@/lib/utils';

export type ConnectorGroupState = 'connected' | 'error' | 'available';

const STATE_ICON: Record<ConnectorGroupState, typeof CheckCircle2> = {
  connected: CheckCircle2,
  error: AlertTriangle,
  available: Plug,
};

const STATE_ICON_TONE: Record<ConnectorGroupState, string> = {
  connected: 'text-success',
  error: 'text-destructive',
  available: 'text-muted-foreground',
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
  /** Optional domain glyph (💡, 📞) — decorative identity, never semantic. */
  glyph?: string;
  t: (key: string) => string;
}

/** Row content rendered INSIDE an `<AccordionTrigger>` (which owns the chevron). */
export function ConnectorGroupTrigger({
  state,
  label,
  count,
  glyph,
  t,
}: ConnectorGroupTriggerProps) {
  const Icon = STATE_ICON[state];
  return (
    <span className="flex flex-1 items-center gap-2 min-w-0 pr-2">
      <Icon className={cn('h-4 w-4 shrink-0', STATE_ICON_TONE[state])} aria-hidden="true" />
      {glyph && <span aria-hidden="true">{glyph}</span>}
      <span className="truncate">{label}</span>
      <span className="text-muted-foreground text-sm shrink-0">({count})</span>
      <span
        className={cn(
          'ml-auto shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium',
          STATE_CHIP_TONE[state]
        )}
      >
        {t(STATE_CHIP_KEY[state])}
      </span>
    </span>
  );
}

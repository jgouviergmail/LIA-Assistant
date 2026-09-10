/**
 * The chat meter's own line — 🟠 IN · 🟢 OUT · 🔵 CACHE · 🟣 GOOGLE, then the
 * euros — so a ticket's figures, a run's and a whole board's read exactly as a
 * message's do (ADR-276). The glyphs are decorative: the labels carry the
 * meaning for a reader who cannot see them.
 */
import { formatEuro, formatNumber } from '@/lib/format';

/** One figure of the meter: its glyph, its label, its value. */
export type Figure = readonly [glyph: string, label: string, value: number];

export interface UsageLineProps {
  figures: readonly Figure[];
  cost: number;
  /** Two for a total, as the conversation pill shows it; six for one run, as a message does. */
  decimals: number;
  className?: string;
}

export function UsageLine({ figures, cost, decimals, className }: UsageLineProps) {
  return (
    <p
      className={
        className ?? 'mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs tabular-nums'
      }
    >
      {figures.map(([glyph, label, value]) => (
        <span key={label} className="whitespace-nowrap">
          <span aria-hidden="true">{glyph} </span>
          {formatNumber(value)} {label}
          <span aria-hidden="true" className="ms-1.5 text-muted-foreground">
            ·
          </span>
        </span>
      ))}
      <span className="whitespace-nowrap font-semibold">{formatEuro(cost, decimals)}</span>
    </p>
  );
}

/** The four figures of a total, in the meter's order. */
export function meterFigures(totals: {
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  google_requests: number;
}): Figure[] {
  return [
    ['🟠', 'IN', totals.tokens_in],
    ['🟢', 'OUT', totals.tokens_out],
    ['🔵', 'CACHE', totals.tokens_cache],
    ['🟣', 'GOOGLE', totals.google_requests],
  ];
}

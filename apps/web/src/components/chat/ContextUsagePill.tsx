/**
 * ContextUsagePill — discreet progress indicator showing how close the
 * conversation is to triggering an automatic compaction.
 *
 * Rendered in the chat header's CENTRED group, at the right of the
 * active-spaces (RAG) indicator, at every viewport width (owner arbitration
 * 2026-08-05 — it was desktop-only for a while and users missed it on
 * phones). Refreshes on every `done` SSE event; tap toggles the tooltip on
 * touch screens.
 *
 * Chrome: the SAME neutral shell as its neighbour the knowledge badge
 * (`ActiveSpacesIndicator`) — `bg-muted/50`, `border-border/60`,
 * `text-muted-foreground`. Owner rule 2026-08-07: a row of header badges where
 * one turns amber then red as the conversation grows reads as an alert about
 * something the user should fix, when it only reports normal progress. The
 * gauge already says it, quietly and continuously.
 *
 * The gauge arc is therefore the ONLY thing that carries the ratio colour:
 *  - ratio <= 0.50  → green
 *  - 0.50 < r <= 0.75 → amber
 *  - 0.75 < r <= 0.90 → orange
 *  - 0.90 < r        → red
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { formatEuro, formatNumber } from '@/lib/format';
import type { ContextUsage } from '@/types/chat-state';

/**
 * Conversation-wide totals folded into the pill tooltip (QW-12) — the header
 * banner that used to carry them cost a full line for figures consulted
 * occasionally. Gating (`tokens_display_enabled`, non-zero tokens) stays on
 * the page side: the pill renders the block iff `totals` is provided.
 */
export interface ConversationTotalsDisplay {
  tokensIn: number;
  tokensOut: number;
  tokensCache: number;
  googleApiRequests: number;
  costEur: number;
  userMessageCount: number;
}

type Props = {
  usage: ContextUsage;
  totals?: ConversationTotalsDisplay | null;
};

/**
 * Chrome shared with the knowledge badge. One string, so the two stay
 * identical: they sit side by side and any drift is visible at a glance.
 */
const BADGE_CHROME =
  'rounded-full border border-border/60 bg-muted/50 px-3 py-1.5 text-muted-foreground shadow-sm';

/** Stroke of the filled arc — the single conditional colour left. */
function ringForRatio(ratio: number): string {
  if (ratio <= 0.5) return 'stroke-green-500 dark:stroke-green-400';
  if (ratio <= 0.75) return 'stroke-amber-500 dark:stroke-amber-400';
  if (ratio <= 0.9) return 'stroke-orange-500 dark:stroke-orange-400';
  return 'stroke-rose-500 dark:stroke-rose-400';
}

function formatTokens(n: number): string {
  if (n >= 1000) {
    const k = n / 1000;
    // 1 decimal only when <10 to keep the pill tight (eg 9.8K vs 38K)
    return k < 10 ? `${k.toFixed(1)}K` : `${Math.round(k)}K`;
  }
  return String(n);
}

export function ContextUsagePill({ usage, totals }: Props) {
  const { t } = useTranslation();
  const [showTooltip, setShowTooltip] = useState(false);

  // Clamp the visual ratio at 1.0 for the ring even if the backend reported
  // a brief overshoot (compaction window). The actual figure stays in the
  // tooltip via `tooltip_overflow`.
  const visualRatio = Math.max(0, Math.min(1, usage.ratio));
  // Badge text is clamped at 100 % so we never display nonsensical values like
  // "150%" inline. The raw overshoot remains accessible in the tooltip, which
  // has the contextual wording the badge can't carry.
  const percent = Math.round(visualRatio * 100);
  const realPercent = Math.round(usage.ratio * 100);
  const ring = ringForRatio(usage.ratio);

  // SVG ring geometry: 16 px circle, 2 px stroke = small but readable.
  const SIZE = 16;
  const STROKE = 2;
  const RADIUS = (SIZE - STROKE) / 2;
  const CIRC = 2 * Math.PI * RADIUS;
  const DASH = CIRC * visualRatio;

  // When the live count has already overshot the threshold (typical right
  // after the response_node generated a long AIMessage), surface the explicit
  // "compaction will run on your next message" wording so the user knows
  // the trigger is queued for the next turn, not stuck.
  // The tooltip shows the real, non-clamped percent so the overshoot stays
  // visible — the badge text on the other hand is clamped.
  const tooltipKey =
    usage.ratio > 1 ? 'chat.context_usage.tooltip_overflow' : 'chat.context_usage.tooltip';
  const tooltip = t(tooltipKey, {
    tokens: usage.tokens.toLocaleString(),
    threshold: usage.threshold.toLocaleString(),
    percent: realPercent,
  });

  return (
    // role="presentation": hover handlers only toggle the visual tooltip —
    // the semantic control is the labelled button inside (audit F012/F045).
    <div
      role="presentation"
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <button
        type="button"
        data-testid="context-usage-pill"
        aria-label={tooltip}
        onClick={() => setShowTooltip(s => !s)}
        className={`flex items-center gap-1.5 ${BADGE_CHROME} transition-colors hover:bg-muted hover:text-foreground`}
      >
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden>
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.2"
            strokeWidth={STROKE}
            className="text-muted-foreground"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={`${DASH} ${CIRC}`}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            className={ring}
          />
        </svg>
        {/* Percentage label — kept always visible. The header bar fits even on
            small phones (360 px) because the badge total width stays ~52 px. */}
        <span className="text-[11px] mobile:text-xs font-semibold text-muted-foreground">
          {percent}%
        </span>
      </button>

      {showTooltip && (
        <div
          role="tooltip"
          className="absolute right-0 top-full mt-1 z-50 rounded-md bg-popover text-popover-foreground border border-border shadow-md px-2 py-1 text-xs"
        >
          <span className="whitespace-nowrap">
            {t('chat.context_usage.tooltip_compact', {
              tokens: formatTokens(usage.tokens),
              threshold: formatTokens(usage.threshold),
              percent: realPercent,
            })}
          </span>
          {totals && (
            // Same token-badge vocabulary (emoji + IN/OUT/CACHE/GOOGLE) as the
            // per-message line in ChatMessage — one consistent economic idiom.
            <div
              data-testid="context-usage-totals"
              className="mt-1 pt-1 border-t border-border flex flex-col gap-0.5"
            >
              <span className="whitespace-nowrap">
                🔢 {formatNumber(totals.tokensIn + totals.tokensOut + totals.tokensCache)} TOTAL
                {' · '}
                <span className="text-orange-500">🟠 {formatNumber(totals.tokensIn)} IN</span>
                {' · '}
                <span className="text-green-600">🟢 {formatNumber(totals.tokensOut)} OUT</span>
              </span>
              <span className="whitespace-nowrap">
                <span className="text-blue-500">🔵 {formatNumber(totals.tokensCache)} CACHE</span>
                {' · '}
                <span className="text-purple-500">
                  🟣 {formatNumber(totals.googleApiRequests)} GOOGLE
                </span>
              </span>
              <span className="whitespace-nowrap font-semibold">
                {totals.userMessageCount}{' '}
                {totals.userMessageCount > 1
                  ? t('chat.page.message_plural')
                  : t('chat.page.message')}
                {' · '}
                {formatEuro(totals.costEur)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

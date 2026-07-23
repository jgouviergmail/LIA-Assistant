'use client';

/**
 * ScrollToBottomButton — floating return affordance of the chat thread
 * (UXR Lot 3, A3).
 *
 * Two modes:
 * - follow mode (default): icon-only, programmatically named — jumps back to
 *   the bottom of the live thread;
 * - historyView (QW-2): labelled "return to the present" and delegated to
 *   `returnToPresent()` by the parent — same semantics as the history banner.
 *
 * The count badge surfaces responses that arrived or completed while the
 * reader was away (detached runs, proactive messages, finished streams). The
 * parent owns positioning (sticky wrapper) and the aria-live announcement.
 */

import { ArrowDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export interface ScrollToBottomButtonProps {
  /** QW-2 history view: labelled mode delegating to return-to-present. */
  historyView: boolean;
  /** New responses while away — renders the badge when > 0. */
  count: number;
  onClick: () => void;
}

export function ScrollToBottomButton({ historyView, count, onClick }: ScrollToBottomButtonProps) {
  const { t } = useTranslation();
  const label = historyView ? t('chat.scroll.return_to_present') : t('chat.scroll.to_bottom');
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-border/40 bg-background/90 px-3 py-1.5 text-xs font-medium text-foreground shadow-lg backdrop-blur hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowDown className="h-3.5 w-3.5" aria-hidden />
      {historyView && <span>{label}</span>}
      {count > 0 && (
        <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
          {t('chat.scroll.new_responses', { count })}
        </span>
      )}
    </button>
  );
}

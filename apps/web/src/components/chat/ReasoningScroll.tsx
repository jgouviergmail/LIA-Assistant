'use client';

/**
 * ReasoningScroll — fixed-height, auto-scrolling container for the live agent
 * reasoning (💭) block streamed during the "thinking" phase.
 *
 * Rendered in place of a `<div class="lia-reasoning">…</div>` sentinel emitted
 * by the SSE reasoning handler (see lib/sse-handlers/handlers.ts). The sentinel
 * carries the reasoning as already-formatted paragraphs (`<p>` children); this
 * component only adds the scroll behaviour + muted styling, so the markdown
 * pipeline (rehype-raw) stays the single source of rendering.
 *
 * Behaviour:
 * - capped height with vertical overflow → the block never pushes the page;
 * - auto-scrolls to the bottom on every content change → the newest thought is
 *   always visible, scrolled smoothly by the browser (no content removal, no
 *   jump — unlike the markdown "pseudo-scroll" it replaces);
 * - bottom fade mask hints there is more above;
 * - the whole block is ephemeral: it is wiped when the answer starts (handled
 *   upstream by clearing the progress message content).
 */

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface ReasoningScrollProps {
  children?: React.ReactNode;
}

export function ReasoningScroll({ children }: ReasoningScrollProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the bottom whenever the streamed content grows.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  });

  return (
    <div
      ref={scrollRef}
      className={cn(
        'lia-reasoning',
        'my-3 max-h-32 overflow-y-auto rounded-md border-l-4 border-primary/30',
        'bg-muted/20 px-3 py-2',
        'text-[13px] italic text-muted-foreground',
        // Bottom fade so older lines dim out as new ones stream in.
        '[mask-image:linear-gradient(to_bottom,transparent_0,black_16px)]'
      )}
    >
      {children}
    </div>
  );
}

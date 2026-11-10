'use client';

/**
 * The last exchanges of the session, both roles, growing while the words
 * arrive (ADR-299, spec A11). Deliberately NOT a live region: what LIA says
 * is already audible, and announcing every fragment would read it twice to a
 * screen-reader user. Folded to its last line unless expanded, so the band
 * stays a band on a phone.
 */
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { LiveCaption } from '@/stores/liveStore';

/** Lines shown when the captions are expanded (older ones are in the thread). */
const EXPANDED_LINES = 8;

export interface LiveCaptionsProps {
  captions: LiveCaption[];
  expanded: boolean;
}

export function LiveCaptions({ captions, expanded }: LiveCaptionsProps) {
  const { t } = useTranslation();
  // A line that shows nothing — a voice's cue alone, its tag removed (ADR-373) —
  // is no line: the last one that said something stays in view.
  const said = captions.filter(caption => caption.text);
  const shown = expanded ? said.slice(-EXPANDED_LINES) : said.slice(-1);
  if (shown.length === 0) return null;
  return (
    <ol className={cn('m-0 flex list-none flex-col gap-0.5 p-0 text-xs', !expanded && 'truncate')}>
      {shown.map(caption => (
        <li key={`${caption.at}-${caption.role}`} className="flex min-w-0 gap-1">
          <span className="shrink-0 font-semibold text-muted-foreground">
            {caption.role === 'user' ? t('live.captions.you') : t('live.captions.lia')}
          </span>
          <span className={cn('min-w-0', !expanded && 'truncate')}>{caption.text}</span>
        </li>
      ))}
    </ol>
  );
}

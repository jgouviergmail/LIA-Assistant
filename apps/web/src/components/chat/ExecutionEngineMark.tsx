'use client';

/**
 * Said under an AUTOMATIC answer (ADR-390): which engine produced it — the
 * pipeline's plan or the ReAct loop — so the person who let LIA choose can see
 * what it chose. An answer whose mode the person picked carries no engine, and
 * the mark renders nothing.
 *
 * It sits on the meta line after the time and a bar (« 18:06 | ReAct », the
 * owner's layout), with the other provenance marks (phone, live session), and
 * next to the token counters it explains: ReAct costs four to eight times what
 * a plan costs. A small themed badge rather than a glyph alone, because the
 * owner asked for the WORD (« ReAct », « Pipeline »); the full sentence is the
 * hover title and what a screen reader hears, the bar being decoration.
 *
 * The meta line never wraps (`whitespace-nowrap`), and on a 320 px phone a date
 * older than a week plus the badge is wider than the bubble. So the space
 * before the bar carries the line's one break opportunity: when the line is
 * too long the bar and the badge drop under the date together, whole, instead
 * of overflowing.
 */

import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { executionEngineOf } from '@/lib/execution-mode';
import { modeIcon } from '@/lib/execution-mode-icon';

export function ExecutionEngineMark({ metadata }: { metadata?: Record<string, unknown> }) {
  const { t } = useTranslation();
  const engine = executionEngineOf(metadata);
  if (!engine) return null;
  const said = t(`chat.execution_engine.said.${engine}`);
  return (
    <span className="whitespace-normal">
      {' '}
      <span className="whitespace-nowrap">
        <span aria-hidden="true">|</span>{' '}
        {/* No vertical padding and a -0.2em drop: measured in Chromium at 390 and
            1280 px, the pill then centres its word on the time's (0 to 0.5 px)
            and leaves the line as tall as a line without it. `align-middle`
            with the default padding grew the line by 3 to 4.5 px and set the
            time 1 to 1.5 px lower than on every other bubble. */}
        <Badge
          size="sm"
          title={said}
          data-execution-engine={engine}
          icon={modeIcon(engine, 'h-3 w-3')}
          className="gap-1 px-1.5 py-0 align-[-0.2em]"
        >
          <span aria-hidden="true">{t(`chat.execution_engine.name.${engine}`)}</span>
          <span className="sr-only">{said}</span>
        </Badge>
      </span>
    </span>
  );
}

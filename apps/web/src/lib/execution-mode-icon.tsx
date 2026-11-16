/**
 * The mark of an execution mode — or of the engine that answered (ADR-070,
 * ADR-390).
 *
 * ONE glyph per idea, read by the chat header's menu, the ticket and routine
 * field and the badge under an automatic answer, so a mode never wears two
 * marks: a flow for the pipeline's plan, a spark for the ReAct loop, a fork for
 * « auto », whose router takes one of the two roads turn by turn.
 *
 * Returns an ELEMENT, never a component type (binding a component during
 * render remounts it every pass — `lib/workboard/icons.tsx` says why), and the
 * glyph is `aria-hidden`: the word beside it always says the same thing.
 */
import { Split, Workflow, Zap } from '@/lib/icons';
import type { ExecutionMode } from '@/lib/execution-mode';

/**
 * Args:
 *   mode: A mode, or an engine (an engine is one of the modes).
 *   className: Sizing and colour, decided by the caller.
 *
 * Returns:
 *   Its glyph.
 */
export function modeIcon(mode: ExecutionMode, className: string): React.ReactNode {
  const shared = { className, 'aria-hidden': true } as const;
  switch (mode) {
    case 'pipeline':
      return <Workflow {...shared} />;
    case 'react':
      return <Zap {...shared} />;
    case 'auto':
      return <Split {...shared} />;
  }
}

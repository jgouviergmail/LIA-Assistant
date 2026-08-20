/**
 * ExpressiveEyes — two solid cartoon eyes, purely presentational.
 *
 * The component only declares state; ALL motion lives in `styles/eyes.css`:
 *  - `data-expression` selects the CSS recipe (lids, squash, loops)
 *  - `data-gesture` plays one idle-life gesture (tilt, bounce, slow blink…)
 *  - `--gaze-x` / `--gaze-y` custom properties aim the gaze ([-1, 1]);
 *    `--gaze-ms` tunes the travel time (a saccade JUMPS, a return eases)
 *  - `is-blinking` runs one blink cycle (the host toggles it on a timer —
 *    never on `animationend`, which jsdom does not emit)
 *  - the size preset scales everything through the container font-size
 *
 * Decorative by contract: `aria-hidden`, no role, no text. The interactive
 * chrome (drag, size, hide) belongs to `EyesWidget`.
 */

import { cn } from '@/lib/utils';
import type { EyeExpression, Gaze, IdleGesture } from '@/components/eyes/expression-engine';
import { DEFAULT_EYE_STYLE, type EyeStyleId } from '@/components/eyes/eye-styles';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import type { CSSProperties } from 'react';

export interface ExpressiveEyesProps {
  expression: EyeExpression;
  /** Directed gaze, or null for a centered/idle gaze. */
  gaze: Gaze | null;
  size: EyesSize;
  /** One blink cycle is running (host-managed transient flag). */
  blinking?: boolean;
  /** Active idle-life gesture (host-managed transient value). */
  gesture?: IdleGesture | null;
  /** Gaze travel time override in ms (saccade jump vs eased return). */
  gazeDurationMs?: number;
  /** Floating emote glyph above the eyes ('?', '!', 'z', '…'), or null. */
  emote?: string | null;
  /** True while the emote plays its leave animation before unmounting. */
  emoteLeaving?: boolean;
  /** Visual style from the eye-style registry (CSS recipe sheet selector). */
  styleId?: EyeStyleId;
  className?: string;
}

function clampAxis(value: number): number {
  return Math.min(1, Math.max(-1, value));
}

export function ExpressiveEyes({
  expression,
  gaze,
  size,
  blinking = false,
  gesture = null,
  gazeDurationMs,
  emote = null,
  emoteLeaving = false,
  styleId = DEFAULT_EYE_STYLE,
  className,
}: ExpressiveEyesProps) {
  const style = {
    '--gaze-x': String(clampAxis(gaze?.x ?? 0)),
    '--gaze-y': String(clampAxis(gaze?.y ?? 0)),
    ...(gazeDurationMs !== undefined ? { '--gaze-ms': `${gazeDurationMs}ms` } : {}),
  } as CSSProperties;

  return (
    <span
      aria-hidden="true"
      data-expression={expression}
      data-style={styleId}
      data-gesture={gesture ?? undefined}
      className={cn('lia-eyes', `lia-eyes--${size}`, blinking && 'is-blinking', className)}
      style={style}
    >
      {emote && (
        <span className={cn('lia-emote', emoteLeaving && 'is-leaving')} data-emote={emote}>
          {emote}
        </span>
      )}
      <span className="lia-eyes-gaze">
        <span className="lia-eye lia-eye--left">
          <span className="lia-eye-blink">
            <span className="lia-eye-shape" />
          </span>
        </span>
        <span className="lia-eye lia-eye--right">
          <span className="lia-eye-blink">
            <span className="lia-eye-shape" />
          </span>
        </span>
      </span>
    </span>
  );
}

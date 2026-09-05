'use client';

/**
 * ExpressiveEyes — two cartoon eyes, declarative on the outside, rigged on
 * the inside.
 *
 * The component states WHAT the character is doing; `useEyesRig` decides HOW
 * it gets there and writes the motion straight onto this node as `--rig-*`
 * custom properties, sixty times a second, without re-rendering anything.
 * The stylesheet consumes those properties and owns everything that is DRAWN
 * rather than moved (silhouette, skin, matter, per-style identity).
 *
 * Two vocabularies on the DOM, and the distinction is the whole architecture:
 *  - `data-*` = STATE the host declares (expression, style, mood family,
 *    gesture, blink, gaze aim). Stable, readable, testable.
 *  - `--rig-*` = MOTION the rig computes. Never declared by a stylesheet.
 *
 * Decorative by contract: `aria-hidden`, no role, no text. The interactive
 * chrome (drag, size, hide) belongs to `EyesWidget`.
 */

import { cn } from '@/lib/utils';
import { clampGazeAxis } from '@/components/eyes/expression-engine';
import type {
  EyeAccessory,
  EyeExpression,
  Gaze,
  IdleGesture,
  IdleMoodFamily,
} from '@/components/eyes/expression-engine';
import { DEFAULT_EYE_STYLE, type EyeStyleId } from '@/components/eyes/eye-styles';
import { useEyesRig } from '@/components/eyes/useEyesRig';
import type { EyesSize } from '@/stores/eyesWidgetStore';

export interface ExpressiveEyesProps {
  expression: EyeExpression;
  /** Directed gaze, or null for a centered/idle gaze. */
  gaze: Gaze | null;
  size: EyesSize;
  /** One blink cycle is running (host-managed transient flag). */
  blinking?: boolean;
  /** Active idle-life gesture (host-managed transient value). */
  gesture?: IdleGesture | null;
  /** Gaze travel time in ms — a saccade jumps, an eased return glides. */
  gazeDurationMs?: number;
  /** Floating emote glyph above the eyes ('?', '!', 'z', '…'), or null. */
  emote?: string | null;
  /** True while the emote plays its leave animation before unmounting. */
  emoteLeaving?: boolean;
  /** Rare one-shot cartoon accessory (a tear, a bead of sweat, a spark). */
  accessory?: EyeAccessory | null;
  /** Visual style from the eye-style registry (CSS recipe sheet selector). */
  styleId?: EyeStyleId;
  /** Mood family pacing the breathing loop and the gesture weights. */
  idleFamily?: IdleMoodFamily;
  /** How forcefully the pose lands, from how the answer was written. */
  emphasis?: number;
  /** Whether the face lives on its own (mimics, sketches). Default true;
   * a preview turns it off to stay comparable. */
  life?: boolean;
  className?: string;
}

/**
 * One eye, and its layer stack — each layer carries exactly one kind of
 * motion, which is what lets a blink, a pose and a breath coexist:
 *
 *   .lia-eye        the eye box: its own travel, and the style's base tilt
 *     .lia-eye-brow the brow, OUTSIDE the lid layer (a lid never clips a brow)
 *     .lia-eye-blink the blink, and nothing else
 *       .lia-eye-shape the pose, the silhouette, and the sustained lids
 *         .lia-eye-pupil dilation and its own deeper gaze parallax
 */
function Eye({ side }: { side: 'left' | 'right' }) {
  return (
    <span className={`lia-eye lia-eye--${side}`}>
      <span className="lia-eye-brow" />
      <span className="lia-eye-blink">
        <span className="lia-eye-shape">
          <span className="lia-eye-pupil" />
        </span>
      </span>
    </span>
  );
}

/** The floating emote glyph above the eyes ('?', '!', 'z', '…'). */
function EyesEmote({ emote, leaving }: { emote: string | null; leaving: boolean }) {
  if (!emote) return null;
  return (
    <span className={cn('lia-emote', leaving && 'is-leaving')} data-emote={emote}>
      {emote}
    </span>
  );
}

/**
 * Fill in what the host left out.
 *
 * A dozen optional props with a default each is a dozen branches, and the
 * complexity ratchet counts them in whatever function holds them. They
 * belong in one pure place rather than in the component, which then has
 * nothing left to decide.
 */
function resolved(props: ExpressiveEyesProps) {
  return {
    blinking: props.blinking ?? false,
    gesture: props.gesture ?? null,
    emote: props.emote ?? null,
    emoteLeaving: props.emoteLeaving ?? false,
    accessory: props.accessory ?? null,
    styleId: props.styleId ?? DEFAULT_EYE_STYLE,
    idleFamily: props.idleFamily ?? 'calm',
    emphasis: props.emphasis ?? 1,
    life: props.life ?? true,
    gazeX: clampGazeAxis(props.gaze?.x ?? 0),
    gazeY: clampGazeAxis(props.gaze?.y ?? 0),
  };
}

export function ExpressiveEyes(props: ExpressiveEyesProps) {
  const { expression, gaze, size, gazeDurationMs, className } = props;
  const view = resolved(props);
  const rootRef = useEyesRig({
    expression,
    styleId: view.styleId,
    family: view.idleFamily,
    gaze,
    gazeDurationMs,
    blinking: view.blinking,
    gesture: view.gesture,
    emphasis: view.emphasis,
    life: view.life,
  });

  return (
    <span
      ref={rootRef}
      aria-hidden="true"
      data-expression={expression}
      data-style={view.styleId}
      data-family={view.idleFamily}
      data-gesture={view.gesture ?? undefined}
      data-blinking={view.blinking ? 'true' : undefined}
      data-gaze-x={view.gazeX}
      data-gaze-y={view.gazeY}
      data-gaze-ms={gazeDurationMs}
      data-life={view.life ? undefined : 'off'}
      className={cn('lia-eyes', `lia-eyes--${size}`, className)}
    >
      <EyesEmote emote={view.emote} leaving={view.emoteLeaving} />
      {view.accessory ? <span className="lia-accessory" data-accessory={view.accessory} /> : null}
      <span className="lia-eyes-gaze">
        <Eye side="left" />
        <Eye side="right" />
      </span>
      {/* The mouth is a sibling of the pair, not a child: it follows the HEAD
          (mass, tilt, shiver) but never the gaze — eyes move inside a face, a
          mouth does not. */}
      <span className="lia-mouth">
        <span className="lia-mouth-shape" />
      </span>
    </span>
  );
}

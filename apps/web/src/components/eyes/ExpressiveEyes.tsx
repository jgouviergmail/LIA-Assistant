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
import { browPath, mouthPath } from '@/components/eyes/rig/face-geometry';
import { strokeContours } from '@/components/eyes/rig/stroke-geometry';
import { resolvePose } from '@/components/eyes/rig/poses';
import { restChannelValues } from '@/components/eyes/rig/channels';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import { AmbientAccessories } from './AmbientAccessories';

export interface ExpressiveEyesProps {
  expression: EyeExpression;
  /** Directed gaze, or null for a centered/idle gaze. */
  gaze: Gaze | null;
  size: EyesSize;
  /** One blink cycle is running (host-managed transient flag). */
  blinking?: boolean;
  /** The running blink MASKS a face swap: the lids hold shut past it. */
  blinkMask?: boolean;
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
  responseWeight?: number;
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
const REST_FACE = restChannelValues();

function Eye({ side, styleId }: { side: 'left' | 'right'; styleId: EyeStyleId }) {
  const rigSide = side === 'left' ? 'L' : 'R';
  const stroke = strokeContours(resolvePose('neutral', styleId), rigSide);
  return (
    <span className={`lia-eye lia-eye--${side}`}>
      <span className="lia-eye-brow">
        <svg viewBox="0 0 100 36" preserveAspectRatio="none" focusable="false">
          <path data-rig-brow={rigSide} d={browPath(REST_FACE, rigSide)} />
        </svg>
      </span>
      <span className="lia-eye-blink">
        <span className="lia-eye-shape">
          <svg
            className="lia-eye-contour"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            focusable="false"
          >
            <path data-rig-stroke={rigSide} d={stroke.upper} strokeWidth={stroke.width} />
            <path
              data-rig-ring={rigSide}
              d={stroke.lower}
              strokeWidth={stroke.width}
              opacity={stroke.lowerOpacity}
            />
          </svg>
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
  const gaze = props.gaze ?? { x: 0, y: 0 };
  return {
    blinking: props.blinking ?? false,
    blinkMask: props.blinkMask ?? false,
    gesture: props.gesture ?? null,
    emote: props.emote ?? null,
    emoteLeaving: props.emoteLeaving ?? false,
    accessory: props.accessory ?? null,
    styleId: props.styleId ?? DEFAULT_EYE_STYLE,
    idleFamily: props.idleFamily ?? 'calm',
    emphasis: props.emphasis ?? 1,
    responseWeight: props.responseWeight ?? 1,
    life: props.life ?? true,
    gazeX: clampGazeAxis(gaze.x),
    gazeY: clampGazeAxis(gaze.y),
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
    blinkMask: view.blinkMask,
    gesture: view.gesture,
    emphasis: view.emphasis,
    responseWeight: view.responseWeight,
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
      data-blink-mask={view.blinking && view.blinkMask ? 'true' : undefined}
      data-gaze-x={view.gazeX}
      data-gaze-y={view.gazeY}
      data-gaze-ms={gazeDurationMs}
      data-life={view.life ? undefined : 'off'}
      className={cn('lia-eyes', `lia-eyes--${size}`, className)}
    >
      <span className="lia-head-shadow" />
      <EyesEmote emote={view.emote} leaving={view.emoteLeaving} />
      <span className="lia-head">
        {view.life ? <AmbientAccessories /> : null}
        {view.styleId === 'smiley' ? <span className="lia-avatar-body" /> : null}
        {view.accessory ? <span className="lia-accessory" data-accessory={view.accessory} /> : null}
        <span className="lia-eyes-gaze">
          <Eye side="left" styleId={view.styleId} />
          <Eye side="right" styleId={view.styleId} />
        </span>
        {/* The jaw and eyes share the head's orientation, with distinct depths.
          Only the eyes perform the faster saccade inside that moving head. */}
        <span className="lia-mouth">
          <svg
            className="lia-mouth-shape"
            viewBox="0 0 100 80"
            preserveAspectRatio="none"
            focusable="false"
          >
            <path data-rig-mouth="" d={mouthPath(REST_FACE)} />
          </svg>
        </span>
      </span>
    </span>
  );
}

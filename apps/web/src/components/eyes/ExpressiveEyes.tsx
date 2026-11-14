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
import { DEFAULT_RIG_EYE_STYLE, type RigEyeStyleId } from '@/components/eyes/eye-styles';
import { useEyesRig } from '@/components/eyes/useEyesRig';
import type { RigCharacterId } from '@/components/eyes/rig/acting-profile';
import {
  browPath,
  mouthPath,
  sculptedBrowPath,
  sculptedMouthContours,
} from '@/components/eyes/rig/face-geometry';
import { strokeContours } from '@/components/eyes/rig/stroke-geometry';
import { resolvePose } from '@/components/eyes/rig/poses';
import { restChannelValues } from '@/components/eyes/rig/channels';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import { AmbientAccessories, SkyAccessories, WrappedScarf } from './AmbientAccessories';
import { useId, type CSSProperties, type ReactNode } from 'react';
import { BodyVolume } from './volume/BodyVolume';
import type { VolumeCharacter } from './volume/volume-geometry';
import { avatarLayoutStyle, type AvatarLayoutProfile } from './layout-profiles';
import type { SpiritVariant } from '@/components/spirit/catalogue';

/** A fixed image's screen projection, in fractions of its complete canvas. */
export interface EyesScreenBounds {
  x: number;
  y: number;
  width: number;
  height: number;
  radius: number;
}

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
  styleId?: RigEyeStyleId;
  /** Acting identity stays distinct from the native skin used by a hybrid. */
  characterId?: RigCharacterId;
  /** Mood family pacing the breathing loop and the gesture weights. */
  idleFamily?: IdleMoodFamily;
  /** How forcefully the pose lands, from how the answer was written. */
  emphasis?: number;
  responseWeight?: number;
  /** Whether the face lives on its own (mimics, sketches). Default true;
   * a preview turns it off to stay comparable. */
  life?: boolean;
  /** False excludes sleep scenes while preserving the rest of the idle life. */
  allowSleep?: boolean;
  /** Explicit local pause for static previews; separate from user motion preference. */
  motionEnabled?: boolean;
  /** Frozen historical portrait uses the same geometry without a live rig clock. */
  staticPose?: boolean;
  /** Decorative screen mask: graphical organs inside, brows free above it. */
  screenBounds?: EyesScreenBounds;
  /** Stationary alpha mask for a textured iris; native skins keep their original DOM. */
  pupilClip?: boolean;
  /** Fixed painted-body boundary for raster-backed faces; brows remain outside it. */
  faceMask?: boolean;
  /** Physical characters reuse the continuous sculpted brow and mouth anatomy. */
  sculptedFace?: boolean;
  /** Anatomical body projection shares the native head and its existing clock. */
  volumeCharacter?: VolumeCharacter;
  volumeVariant?: SpiritVariant;
  /** Model/gender landmarks place decorative props without another motion owner. */
  layoutProfile?: AvatarLayoutProfile;
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
const SCULPTED_REST_MOUTH = sculptedMouthContours(REST_FACE);

function EyeBrow({ side, sculpted = false }: { side: 'L' | 'R'; sculpted?: boolean }) {
  return (
    <span className="lia-eye-brow">
      <svg viewBox="0 0 100 36" preserveAspectRatio="none" focusable="false">
        <path
          data-rig-brow={side}
          data-rig-brow-shape={sculpted ? 'sculpted' : undefined}
          d={sculpted ? sculptedBrowPath(REST_FACE, side) : browPath(REST_FACE, side)}
        />
      </svg>
    </span>
  );
}

function Eye({
  side,
  styleId,
  showBrow = true,
  pupilClip = false,
}: {
  side: 'left' | 'right';
  styleId: RigEyeStyleId;
  showBrow?: boolean;
  pupilClip?: boolean;
}) {
  const rigSide = side === 'left' ? 'L' : 'R';
  const stroke = strokeContours(resolvePose('neutral', styleId), rigSide);
  return (
    <span className={`lia-eye lia-eye--${side}`}>
      {showBrow ? <EyeBrow side={rigSide} /> : null}
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
          {pupilClip ? (
            <span className="lia-eye-pupil-clip">
              <span className="lia-eye-pupil" />
            </span>
          ) : (
            <span className="lia-eye-pupil" />
          )}
        </span>
      </span>
    </span>
  );
}

function EyePair({
  styleId,
  showBrow = true,
  pupilClip = false,
  volume = false,
}: {
  styleId: RigEyeStyleId;
  showBrow?: boolean;
  pupilClip?: boolean;
  volume?: boolean;
}) {
  return (
    <span className="lia-eyes-gaze">
      <OrganSurface kind="left" volume={volume}>
        <Eye side="left" styleId={styleId} showBrow={showBrow} pupilClip={pupilClip} />
      </OrganSurface>
      <OrganSurface kind="right" volume={volume}>
        <Eye side="right" styleId={styleId} showBrow={showBrow} pupilClip={pupilClip} />
      </OrganSurface>
    </span>
  );
}

/** Each native organ retains its own layers inside a projected surface tangent. */
function OrganSurface({
  kind,
  children,
  volume = false,
}: {
  kind: 'left' | 'right' | 'mouth';
  children: ReactNode;
  volume?: boolean;
}) {
  if (volume)
    return (
      <span className={`lia-volume-surface lia-volume-surface--${kind}`} data-volume-surface={kind}>
        {children}
      </span>
    );
  return children;
}

function Mouth({ sculpted = false }: { sculpted?: boolean }) {
  const id = useId();
  return (
    <span className="lia-mouth">
      <svg
        className="lia-mouth-shape"
        viewBox="0 0 100 80"
        preserveAspectRatio="none"
        focusable="false"
      >
        {sculpted ? (
          <defs>
            <linearGradient id={`${id}-cavity`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#8d4725" />
              <stop offset="0.45" stopColor="#30170f" />
              <stop offset="1" stopColor="#a34c2c" />
            </linearGradient>
            <linearGradient id={`${id}-teeth`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#d7b79b" />
              <stop offset="0.35" stopColor="#fffcef" />
              <stop offset="1" stopColor="#eddec5" />
            </linearGradient>
            <linearGradient id={`${id}-tongue`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#e58d78" />
              <stop offset="1" stopColor="#b04a32" />
            </linearGradient>
            <clipPath id={`${id}-mouth-window`}>
              <use href={`#${id}-mouth-ink`} />
            </clipPath>
          </defs>
        ) : null}
        <path
          id={`${id}-mouth-ink`}
          data-rig-mouth=""
          data-rig-mouth-shape={sculpted ? 'sculpted' : undefined}
          d={sculpted ? SCULPTED_REST_MOUTH.cavity : mouthPath(REST_FACE)}
          fill={sculpted ? `url(#${id}-cavity)` : undefined}
        />
        {sculpted ? (
          <g clipPath={`url(#${id}-mouth-window)`}>
            <path
              data-rig-mouth-teeth=""
              d={SCULPTED_REST_MOUTH.teeth}
              fill={`url(#${id}-teeth)`}
            />
            <path
              data-rig-mouth-tongue=""
              d={SCULPTED_REST_MOUTH.tongue}
              fill={`url(#${id}-tongue)`}
            />
          </g>
        ) : null}
      </svg>
    </span>
  );
}

function FaceOrgans({
  styleId,
  screen,
  pupilClip,
  faceMask,
  sculpted,
  volume,
}: {
  styleId: RigEyeStyleId;
  screen: boolean;
  pupilClip?: boolean;
  faceMask?: boolean;
  sculpted: boolean;
  volume: boolean;
}) {
  if (faceMask)
    return (
      <>
        <span className="lia-raster-face-mask">
          <EyePair styleId={styleId} showBrow={false} pupilClip={pupilClip} volume={volume} />
          <OrganSurface kind="mouth" volume={volume}>
            <Mouth sculpted={sculpted} />
          </OrganSurface>
        </span>
        <span className="lia-raster-brows">
          <span className="lia-eyes-gaze">
            <OrganSurface kind="left" volume={volume}>
              <span className="lia-eye lia-eye--left">
                <EyeBrow side="L" sculpted={sculpted} />
              </span>
            </OrganSurface>
            <OrganSurface kind="right" volume={volume}>
              <span className="lia-eye lia-eye--right">
                <EyeBrow side="R" sculpted={sculpted} />
              </span>
            </OrganSurface>
          </span>
        </span>
      </>
    );
  if (!screen)
    return (
      <>
        <EyePair styleId={styleId} pupilClip={pupilClip} volume={volume} />
        <OrganSurface kind="mouth" volume={volume}>
          <Mouth sculpted={sculpted} />
        </OrganSurface>
      </>
    );
  return (
    <>
      <span className="lia-monitor-screen">
        <span className="lia-monitor-face-content">
          <EyePair styleId={styleId} showBrow={false} pupilClip={pupilClip} volume={volume} />
          <OrganSurface kind="mouth" volume={volume}>
            <Mouth />
          </OrganSurface>
        </span>
      </span>
      <span className="lia-monitor-brows">
        <span className="lia-monitor-face-content">
          <span className="lia-eyes-gaze">
            <OrganSurface kind="left" volume={volume}>
              <span className="lia-eye lia-eye--left">
                <EyeBrow side="L" sculpted />
              </span>
            </OrganSurface>
            <OrganSurface kind="right" volume={volume}>
              <span className="lia-eye lia-eye--right">
                <EyeBrow side="R" sculpted />
              </span>
            </OrganSurface>
          </span>
        </span>
      </span>
    </>
  );
}

type ScreenStyle = CSSProperties & Record<`--screen-${string}`, string>;

function screenStyle(bounds?: EyesScreenBounds): ScreenStyle | undefined {
  if (!bounds) return;
  return {
    '--screen-left': `${bounds.x * 100}%`,
    '--screen-top': `${bounds.y * 100}%`,
    '--screen-width': `${bounds.width * 100}%`,
    '--screen-height': `${bounds.height * 100}%`,
    '--screen-radius': `calc(var(--monitor-size) * ${bounds.radius})`,
  };
}

function avatarPresentation(props: ExpressiveEyesProps) {
  const profile = props.volumeCharacter ? props.layoutProfile : undefined;
  const screen = screenStyle(props.screenBounds);
  return {
    family: profile?.family,
    variant: profile?.variant,
    style: { ...screen, ...(profile ? avatarLayoutStyle(profile) : undefined) },
  };
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

/** Appearance changes wake the same writer; inactive previews keep their bake. */
function volumePresentation(props: ExpressiveEyesProps) {
  const {
    volumeCharacter: character,
    volumeVariant: variant = 'male',
    motionEnabled = true,
    staticPose = false,
  } = props;
  return {
    character,
    variant,
    attributeVariant: character ? variant : undefined,
    ready: character ? 'false' : undefined,
    enabled: motionEnabled && !staticPose,
    appearanceKey: character ? variant : undefined,
  };
}

function VolumeLayers({
  appearance,
  size,
}: {
  appearance: ReturnType<typeof volumePresentation>;
  size: EyesSize;
}) {
  if (!appearance.character) return null;
  return (
    <BodyVolume
      character={appearance.character}
      variant={appearance.variant}
      size={size}
      enabled={appearance.enabled}
    />
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
    styleId: props.styleId ?? DEFAULT_RIG_EYE_STYLE,
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
  const volume = volumePresentation(props);
  const avatar = avatarPresentation(props);
  const scarfFit = props.volumeCharacter ? props.layoutProfile?.scarf : undefined;
  const rootRef = useEyesRig({
    expression,
    styleId: view.styleId,
    characterId: props.characterId,
    family: view.idleFamily,
    gaze,
    gazeDurationMs,
    blinking: view.blinking,
    blinkMask: view.blinkMask,
    gesture: view.gesture,
    emphasis: view.emphasis,
    responseWeight: view.responseWeight,
    life: view.life,
    allowSleep: props.allowSleep,
    motionEnabled: props.motionEnabled,
    staticPose: props.staticPose,
    appearanceKey: volume.appearanceKey,
    idleScale: size === 'xl' ? 44 / 64 : 1,
  });

  return (
    <span
      ref={rootRef}
      aria-hidden="true"
      data-expression={expression}
      data-style={view.styleId}
      data-volume-character={volume.character}
      data-volume-variant={volume.attributeVariant}
      data-volume-ready={volume.ready}
      data-avatar-layout={avatar.family}
      data-avatar-variant={avatar.variant}
      data-family={view.idleFamily}
      data-gesture={view.gesture ?? undefined}
      data-blinking={view.blinking ? 'true' : undefined}
      data-blink-mask={view.blinking && view.blinkMask ? 'true' : undefined}
      data-gaze-x={view.gazeX}
      data-gaze-y={view.gazeY}
      data-gaze-ms={gazeDurationMs}
      data-life={view.life ? undefined : 'off'}
      data-motion={props.motionEnabled === false ? 'off' : undefined}
      className={cn('lia-eyes', `lia-eyes--${size}`, className)}
      style={avatar.style}
    >
      {view.life ? <SkyAccessories /> : null}
      <span className="lia-head-shadow" />
      <span className="lia-body-motion">
        <EyesEmote emote={view.emote} leaving={view.emoteLeaving} />
        {view.life ? <WrappedScarf fit={scarfFit} /> : null}
        <span className="lia-head">
          {view.life ? <AmbientAccessories fit={scarfFit} /> : null}
          <VolumeLayers appearance={volume} size={size} />
          {view.accessory ? (
            <span className="lia-accessory" data-accessory={view.accessory} />
          ) : null}
          {/* Skin boundaries clip graphical organs while the same head carries
          every projection. Brows remain free above the face boundary. */}
          <FaceOrgans
            styleId={view.styleId}
            screen={Boolean(props.screenBounds)}
            pupilClip={props.pupilClip}
            faceMask={props.faceMask}
            sculpted={Boolean(props.sculptedFace)}
            volume={Boolean(volume.character)}
          />
        </span>
      </span>
    </span>
  );
}

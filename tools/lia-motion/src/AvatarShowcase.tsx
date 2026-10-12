import React, { useId, useMemo, type CSSProperties } from 'react';
import { Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

// The film projects the product's actual expression recipes and continuous
// contours. Only its clock is replaced: every pose is sampled from video time.
import {
  CHANNEL_KEYS,
  CHANNELS,
  type ChannelValues,
} from '../../../apps/web/src/components/eyes/rig/channels';
import { resolvePose } from '../../../apps/web/src/components/eyes/rig/poses';
import {
  browPath,
  mouthPath,
  sculptedBrowPath,
  sculptedMouthContours,
} from '../../../apps/web/src/components/eyes/rig/face-geometry';
import { strokeContours } from '../../../apps/web/src/components/eyes/rig/stroke-geometry';
import { springStep, type SpringState } from '../../../apps/web/src/components/eyes/rig/spring';
import { speechTapes } from '../../../apps/web/src/components/eyes/rig/speech';
import { tapeTargetAt } from '../../../apps/web/src/components/eyes/rig/tape';
import { smileyMouthWidth } from '../../../apps/web/src/components/eyes/smiley/rest-mouth';
import type { RigEyeStyleId } from '../../../apps/web/src/components/eyes/eye-styles';
import type { EyeExpression } from '../../../apps/web/src/components/eyes/expression-engine';
import { MONITOR_SCREEN } from '../../../apps/web/src/components/eyes/monitor-geometry';

const INK = '#f4f6ff';
const MUTED = '#b7bed4';
const CYAN = '#78ddfa';
const VIOLET = '#b4a0ff';
const CYCLE_SECONDS = 16;
const clamp = (value: number, minimum = 0, maximum = 1) =>
  Math.min(maximum, Math.max(minimum, value));

const BEATS: ReadonlyArray<{
  at: number;
  expression: EyeExpression;
  label: string;
  mood: string;
  gaze: readonly [number, number];
}> = [
  { at: 0, expression: 'attentive', label: 'À l’écoute', mood: 'Curieuse', gaze: [-0.28, 0.04] },
  { at: 4, expression: 'thinking', label: 'En réflexion', mood: 'Concentrée', gaze: [0.4, -0.32] },
  { at: 7, expression: 'speaking', label: 'LIA parle', mood: 'Engagée', gaze: [-0.08, 0.02] },
  { at: 12.5, expression: 'joy', label: 'Un peu de joie', mood: 'Enjouée', gaze: [-0.22, 0.04] },
];

function beatAt(seconds: number) {
  return BEATS.reduce((current, beat) => (seconds >= beat.at ? beat : current), BEATS[0]);
}

function seededRandom(seed: number) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

/** Pre-sample native analytic springs, including seeded native speech tapes.
 * No requestAnimationFrame, wall clock, network, audio provider or random draw
 * occurs in render, so a seek and a parallel video render produce the same face.
 */
function sampleNativeRig(style: RigEyeStyleId, fps: number): ChannelValues[] {
  const poses = BEATS.map(beat => resolvePose(beat.expression, style));
  const initial = poses[0];
  const motion = Object.fromEntries(
    CHANNEL_KEYS.map(key => [key, { value: initial[key], velocity: 0 }])
  ) as Record<keyof ChannelValues, SpringState>;
  const tapes = speechTapes(seededRandom(4917));
  const samples: ChannelValues[] = [];
  for (let frame = 0; frame < CYCLE_SECONDS * fps; frame++) {
    const seconds = frame / fps;
    const beat = beatAt(seconds);
    const target = { ...poses[BEATS.indexOf(beat)] };
    target.gazeX = beat.gaze[0];
    target.gazeY = beat.gaze[1];
    target.headYaw = target.gazeX * 0.28;
    target.headPitch = target.gazeY * 0.3;
    target.mass = 1 + Math.sin(seconds * 1.5) * 0.009;
    const blinking = [1.85, 5.55, 9.35, 14.05].some(at => seconds >= at && seconds < at + 0.105);
    target.blinkL = blinking ? 1 : 0;
    target.blinkR = target.blinkL;
    if (beat.expression === 'speaking') {
      const speechMs = (seconds - beat.at) * 1000;
      for (const tape of tapes) {
        const value = tapeTargetAt(tape, speechMs);
        if (value !== null)
          target[tape.channel] = (tape.relative ? target[tape.channel] : 0) + value;
      }
    }
    const sample = { ...initial };
    for (const key of CHANNEL_KEYS) {
      const channel = CHANNELS[key];
      const frequency =
        channel.group === 'blink'
          ? 13
          : channel.group === 'mouth'
            ? 7
            : channel.group === 'gaze'
              ? 4.8
              : 3.4;
      motion[key] = springStep(motion[key], target[key], { frequency, damping: 0.85 }, 1000 / fps);
      sample[key] = motion[key].value;
    }
    sample.mouthArc = Math.abs(sample.mouthCurve);
    samples.push(sample);
  }
  return samples;
}

const CHARACTER_GEOMETRY = {
  bip: {
    version: 1,
    eyeY: 0.43,
    mouthY: 0.56,
    eyeW: 0.54 / 2.6,
    gap: 0.055 / 2.6,
    mouthW: 0.58 / 2.6,
    ink: '#60e2ff',
  },
  spirit: {
    version: 2,
    eyeY: 0.52405,
    mouthY: 0.6543,
    eyeW: 0.59265 / 2.6,
    gap: 0.01912 / 2.6,
    mouthW: 0.48 / 2.6,
    ink: '#2c2944',
  },
  moss: {
    version: 2,
    eyeY: 0.52405,
    mouthY: 0.6543,
    eyeW: 0.59265 / 2.6,
    gap: 0.01912 / 2.6,
    mouthW: 0.48 / 2.6,
    ink: '#26413c',
  },
  lumen: {
    version: 2,
    eyeY: 0.52405,
    mouthY: 0.6543,
    eyeW: 0.59265 / 2.6,
    gap: 0.01912 / 2.6,
    mouthW: 0.48 / 2.6,
    ink: '#543735',
  },
  nimbo: {
    version: 1,
    eyeY: 0.49,
    mouthY: 0.61,
    eyeW: 0.59265 / 2.6,
    gap: 0.01912 / 2.6,
    mouthW: 0.62 / 2.6,
    ink: '#392b40',
  },
  orbit: {
    version: 1,
    eyeY: 0.48,
    mouthY: 0.6,
    eyeW: 0.59265 / 2.6,
    gap: 0.01912 / 2.6,
    mouthW: 0.58 / 2.6,
    ink: '#172735',
  },
  boulon: {
    version: 1,
    eyeY: 0.43,
    mouthY: 0.55,
    eyeW: 0.425 / 2.6,
    gap: 0.06 / 2.6,
    mouthW: 0.58 / 2.6,
    ink: '#543020',
  },
  oscar: {
    version: 1,
    eyeY: 0.354,
    mouthY: 0.5,
    eyeW: 0.385 / 2.6,
    gap: 0.075 / 2.6,
    mouthW: 0.54 / 2.6,
    ink: '#874e45',
  },
} as const;

type Character = keyof typeof CHARACTER_GEOMETRY;
type NativeAvatarProps = {
  kind: Character | 'smiley';
  size: number;
  values: ChannelValues;
  variant?: 'male' | 'female';
  cleanAlpha?: boolean;
  bodyAssetOverride?: string;
  grounded?: boolean;
  /** Film-only BIP articulation: the original head turns above fixed feet. */
  headTurnOnly?: boolean;
};

export type NativeAvatarKind = NativeAvatarProps['kind'];

function FaceMouth({
  values,
  sculpted,
  color,
  width,
  height,
  top,
}: {
  values: ChannelValues;
  sculpted: boolean;
  color: string;
  width: number;
  height: number;
  top: number;
}) {
  const id = useId();
  const anatomy = sculptedMouthContours(values);
  return (
    <svg
      viewBox="0 0 100 80"
      preserveAspectRatio="none"
      style={{
        position: 'absolute',
        width,
        height,
        left: '50%',
        top,
        transform: 'translateX(-50%)',
        overflow: 'visible',
      }}
    >
      {sculpted ? (
        <>
          <defs>
            <linearGradient id={`${id}-cavity`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#8d4725" />
              <stop offset=".45" stopColor="#30170f" />
              <stop offset="1" stopColor="#a34c2c" />
            </linearGradient>
            <linearGradient id={`${id}-teeth`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#d7b79b" />
              <stop offset=".35" stopColor="#fffcef" />
              <stop offset="1" stopColor="#eddec5" />
            </linearGradient>
            <clipPath id={`${id}-mouth-window`}>
              <path d={anatomy.cavity} />
            </clipPath>
          </defs>
          <path d={anatomy.cavity} fill={`url(#${id}-cavity)`} stroke={color} strokeWidth={0.65} />
          <g clipPath={`url(#${id}-mouth-window)`}>
            <path d={anatomy.teeth} fill={`url(#${id}-teeth)`} />
            <path d={anatomy.tongue} fill="#dc7183" />
          </g>
        </>
      ) : (
        <path d={mouthPath(values)} fill={color} />
      )}
    </svg>
  );
}

/** Material and static landmarks are selected independently of the live pose. */
function nativeAvatarGeometry(kind: NativeAvatarProps['kind'], variant: 'female' | 'male') {
  if (kind === 'smiley') {
    return {
      eyeY: (0.65 + 0.42) / 2.6,
      mouthY: 1.22 / 2.6,
      eyeW: 0.84 / 2.6,
      gap: 0.12 / 2.6,
      mouthW: 1.45 / 2.6,
      ink: '#59331d',
      browWidthRatio: 0.92,
      browHeightEm: variant === 'female' ? 0.17 : 0.28,
      bodyAsset: 'avatars/smiley/v1/body.webp',
      bodyTransform: 'none',
      gazeXScale: 0.025,
      gazeYScale: 0.0173,
      mouthHeightEm: 0.95,
    };
  }
  const geometry = CHARACTER_GEOMETRY[kind];
  return {
    ...geometry,
    eyeW: kind === 'bip' && variant === 'male' ? 0.57 / 2.6 : geometry.eyeW,
    gap: kind === 'bip' && variant === 'male' ? 0.06 / 2.6 : geometry.gap,
    browWidthRatio: 0.72,
    browHeightEm: kind === 'bip' ? 0.15 : kind === 'oscar' ? 0.057 : 0.085,
    bodyAsset: `avatars/${kind}/v${geometry.version}/${variant}/body.webp`,
    bodyTransform: 'scale(1.13)',
    gazeXScale: kind === 'oscar' ? 0 : 0.0115,
    gazeYScale: kind === 'oscar' ? 0 : 0.0077,
    mouthHeightEm: 0.45,
  };
}

function nativeAlphaMask(bodyAsset: string, enabled: boolean): CSSProperties {
  if (!enabled) return {};
  // The published RGBA silhouette is its own mask. This removes the near-zero
  // alpha compression fog made visible by an editorial enlargement, without
  // drawing or replacing any body pixel or importing an invented silhouette.
  const source = `url("${staticFile(bodyAsset)}")`;
  return {
    maskImage: source,
    WebkitMaskImage: source,
    maskSize: '100% 100%',
    WebkitMaskSize: '100% 100%',
    maskRepeat: 'no-repeat',
    WebkitMaskRepeat: 'no-repeat',
  };
}

function NativeAvatar({
  kind,
  size,
  values,
  variant = 'female',
  cleanAlpha = false,
  bodyAssetOverride,
  grounded = false,
  headTurnOnly = false,
}: NativeAvatarProps) {
  const smiley = kind === 'smiley';
  const geometry = { ...nativeAvatarGeometry(kind, variant), ...(bodyAssetOverride ? { bodyAsset: bodyAssetOverride } : {}) };
  const eyeWidth = size * geometry.eyeW;
  const eyeGap = geometry.gap;
  const eyeTop = size * geometry.eyeY - eyeWidth / 2;
  const browWidth = eyeWidth * geometry.browWidthRatio;
  const browHeight = (size / 2.6) * geometry.browHeightEm;
  const faceX = values.gazeX * size * geometry.gazeXScale;
  const faceY = values.gazeY * size * geometry.gazeYScale;
  const mouthWidth = size * geometry.mouthW * (smiley ? smileyMouthWidth(values) : values.mouthW);
  const mouthTop = smiley ? size * geometry.mouthY : size * geometry.mouthY - (size * 0.21) / 2.6;
  const articulatedHead = headTurnOnly && kind === 'bip' && variant === 'male';
  // BIP's published painting has a real collar below the oversized head.
  // Both layers read the SAME untouched PNG; a narrow native collar overlap
  // avoids a subpixel crack while its head turns. No new silhouette or pixels.
  const artwork: CSSProperties = {
    position: 'absolute', left:0, top:0, width:size, height:size,
    transform:geometry.bodyTransform, objectFit:'contain',
    ...nativeAlphaMask(geometry.bodyAsset,cleanAlpha),
  };
  const head: CSSProperties = {
    position: 'relative',
    width: size,
    height: size,
    transform: `translateY(${(values.massY * size) / 2.6}px) rotate(${values.tilt}deg) rotateY(${values.headYaw * (articulatedHead?24:16)}deg) rotateX(${-values.headPitch * 10}deg) scale(${values.mass})`,
    transformStyle: 'preserve-3d',
    transformOrigin: articulatedHead ? '50% 68.2%' : grounded ? '50% 89%' : undefined,
    zIndex: articulatedHead?1:undefined,
  };
  return (
    <div style={{ position:'relative',width: size, height: size, perspective: size * (articulatedHead?2.8:6) }} aria-hidden="true">
      {articulatedHead?<Img src={staticFile(geometry.bodyAsset)} style={{...artwork,clipPath:'inset(65.6% 0 0 0)'}}/>:null}
      <div style={head}>
        <Img
          src={staticFile(geometry.bodyAsset)}
          style={{...artwork,...(articulatedHead?{clipPath:'inset(0 0 34.1% 0)'}:{})}}
        />
        {smiley && variant === 'female' ? (
          <Img
            src={staticFile('avatars/smiley/v1/bow.webp')}
            style={{
              position: 'absolute',
              width: size * 0.43,
              height: size * 0.43,
              left: size * 0.05,
              top: -size * 0.1,
              transform: 'rotate(-13deg)',
            }}
          />
        ) : null}
        <div
          style={{ position: 'absolute', inset: 0, transform: `translate(${faceX}px, ${faceY}px)` }}
        >
          {(['L', 'R'] as const).map(side => {
            const blink = clamp(values[`blink${side}`]);
            const x =
              size / 2 + ((side === 'L' ? -1 : 1) * (eyeWidth + size * eyeGap)) / 2 - eyeWidth / 2;
            const squint = smiley
              ? Math.max(0, 1 - values[`sy${side}`])
              : Math.max(0, 1 - values[`sy${side}`]) * 0.35;
            const topLid = values[`lidTop${side}`] + squint * values[`oy${side}`];
            const bottomLid = values[`lidBot${side}`] + squint * (100 - values[`oy${side}`]);
            const textureBase = smiley ? 'avatars/smiley/v1' : `avatars/spirit/v1/${variant}`;
            const eyeAsset = `${textureBase}/${!smiley && side === 'R' ? 'eye-right' : 'eye'}.webp`;
            const maskAsset = `${textureBase}/${!smiley && side === 'R' ? 'sclera-mask-right' : 'sclera-mask'}.webp`;
            const assetMask = `url("${staticFile(eyeAsset)}") center / contain no-repeat`;
            const pupilMask = `url("${staticFile(maskAsset)}") center / contain no-repeat`;
            return (
              <React.Fragment key={side}>
                <div
                  style={{
                    position: 'absolute',
                    left: x,
                    top: eyeTop,
                    width: eyeWidth,
                    height: eyeWidth,
                    transform: `scaleX(${values[`sx${side}`]}) rotate(${values[`rot${side}`]}deg)`,
                    clipPath: `inset(${clamp(topLid, 0, 50)}% 0 ${clamp(bottomLid, 0, 50)}% 0 round ${size * 0.012}px)`,
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      clipPath: `inset(${blink * 54}% 0 ${blink * 46}% 0 round ${size * 0.015}px)`,
                    }}
                  >
                    {kind === 'bip' ? (
                      <div
                        style={{
                          position: 'absolute',
                          inset: 0,
                          background:
                            'radial-gradient(ellipse at 32% 18%, rgba(231,253,255,.9), transparent 26%), radial-gradient(ellipse at 50% 48%, #effeff 24%, #90eeff 64%, #279de0 94%)',
                          mask: assetMask,
                          WebkitMask: assetMask,
                        }}
                      />
                    ) : (
                      <Img
                        src={staticFile(eyeAsset)}
                        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
                      />
                    )}
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        mask: pupilMask,
                        WebkitMask: pupilMask,
                      }}
                    >
                      <Img
                        src={staticFile(`${textureBase}/iris.webp`)}
                        style={{
                          position: 'absolute',
                          inset: 0,
                          width: '100%',
                          height: '100%',
                          transform: `translate(${values.gazeX * size * (smiley ? 0.027 : 0.0173)}px, ${values.gazeY * size * 0.014}px) scale(${clamp(values[`pupil${side}`], 0.92, 1.08)})`,
                        }}
                      />
                    </div>
                  </div>
                </div>
                <svg
                  viewBox="0 0 100 36"
                  preserveAspectRatio="none"
                  style={{
                    position: 'absolute',
                    width: browWidth,
                    height: browHeight,
                    left: x + (eyeWidth - browWidth) / 2 + (values[`browX${side}`] * size) / 2.6,
                    top:
                      eyeTop +
                      (eyeWidth *
                        (values[`oy${side}`] * (1 - values[`sy${side}`]) +
                          values[`lidTop${side}`] * values[`sy${side}`])) /
                        100 -
                      browHeight * (smiley ? 1 : 0.5) -
                      (smiley ? (size * 0.06) / 2.6 : 0) +
                      (values[`browY${side}`] * size) / 2.6,
                    overflow: 'visible',
                  }}
                >
                  {kind === 'bip' ? (
                    <path
                      d={browPath(values, side)}
                      fill="none"
                      stroke={geometry.ink}
                      strokeWidth="5"
                      strokeLinecap="round"
                    />
                  ) : (
                    <path d={sculptedBrowPath(values, side)} fill={geometry.ink} />
                  )}
                </svg>
              </React.Fragment>
            );
          })}
          <FaceMouth
            values={values}
            sculpted={kind !== 'bip'}
            color={geometry.ink}
            width={mouthWidth}
            height={(size / 2.6) * geometry.mouthHeightEm}
            top={mouthTop}
          />
        </div>
      </div>
    </div>
  );
}

/** Native product character alone, without the former illustrative UI frame. */
export function NativeCharacter({
  kind = 'bip',
  size,
  frame: suppliedFrame,
  variant = 'male',
}: {
  kind?: Character | 'smiley';
  size: number;
  frame?: number;
  variant?: 'male' | 'female';
}) {
  const currentFrame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const style = kind === 'smiley' ? 'smiley' : 'billes';
  const samples = useMemo(() => sampleNativeRig(style, fps), [style, fps]);
  const frame = Math.floor(Math.max(0, suppliedFrame ?? currentFrame)) % samples.length;
  return (
    <NativeAvatar kind={kind} size={size} variant={variant} values={samples[frame]} cleanAlpha />
  );
}

/** Narrative-only native sampling: attentive → thinking → attentive → joy.
 * The soundtrack has no voice, so this deliberately has no speech tape. The
 * original showcase cycle above remains unchanged. */
function sampleStoryRig(fps: number): ChannelValues[] {
  const recipes = [
    { at: 0, expression: 'attentive' as const, gaze: [0.38, -0.06] },
    { at: 6.701, expression: 'thinking' as const, gaze: [0.42, -0.22] },
    { at: 12.857, expression: 'attentive' as const, gaze: [0.36, -0.03] },
    { at: 18.489, expression: 'joy' as const, gaze: [0.12, 0.02] },
  ];
  const poses = recipes.map(recipe => resolvePose(recipe.expression, 'billes'));
  const motion = Object.fromEntries(
    CHANNEL_KEYS.map(key => [key, { value: poses[0][key], velocity: 0 }])
  ) as Record<keyof ChannelValues, SpringState>;
  const samples: ChannelValues[] = [];
  for (let frame = 0; frame < 24 * fps; frame++) {
    const seconds = frame / fps;
    const recipe = recipes.reduce((current, next) => seconds >= next.at ? next : current, recipes[0]);
    const target = { ...poses[recipes.indexOf(recipe)] };
    target.gazeX = recipe.gaze[0];
    target.gazeY = recipe.gaze[1];
    target.headYaw = target.gazeX * 0.28;
    target.headPitch = target.gazeY * 0.3;
    target.mass = 1 + Math.sin(seconds * 1.5) * 0.006;
    const blink = [1.85, 5.55, 9.35, 14.05, 18.3, 22.35].some(at => seconds >= at && seconds < at + 0.105);
    target.blinkL = blink ? 1 : 0;
    target.blinkR = target.blinkL;
    const sample = { ...poses[0] };
    for (const key of CHANNEL_KEYS) {
      const frequency = CHANNELS[key].group === 'blink' ? 13 : CHANNELS[key].group === 'gaze' ? 4.8 : 3.4;
      motion[key] = springStep(motion[key], target[key], { frequency, damping: 0.85 }, 1000 / fps);
      sample[key] = motion[key].value;
    }
    sample.mouthArc = Math.abs(sample.mouthCurve);
    samples.push(sample);
  }
  return samples;
}

export function NativeStoryCharacter({ size, frame: suppliedFrame, bodyAsset = 'mascot-film/bip-male-original.png' }: { size: number; frame?: number; bodyAsset?: string }) {
  const currentFrame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const samples = useMemo(() => sampleStoryRig(fps), [fps]);
  const frame = Math.min(samples.length - 1, Math.floor(Math.max(0, suppliedFrame ?? currentFrame)));
  return <NativeAvatar kind="bip" size={size} variant="male" values={samples[frame]} cleanAlpha bodyAssetOverride={bodyAsset} />;
}

/** Presentation-only adapter: the original artwork and product face renderer
 * remain native; a film may supply a deterministic, non-speaking pose. */
export function NativeStoryPose({ size, values,headTurnOnly=true }: { size: number; values: ChannelValues;headTurnOnly?:boolean }) {
  return <NativeAvatar kind="bip" size={size} variant="male" values={values} cleanAlpha grounded headTurnOnly={headTurnOnly} bodyAssetOverride="mascot-film/bip-male-original.png" />;
}

/** The film may author contexts while retaining the published body and face. */
export function NativeAvatarPose({ kind, size, values, variant = 'male' }: {
  kind: NativeAvatarKind;
  size: number;
  values: ChannelValues;
  variant?: 'male' | 'female';
}) {
  return <NativeAvatar kind={kind} size={size} variant={variant} values={values} cleanAlpha grounded />;
}

const MONITOR_STYLES: readonly RigEyeStyleId[] = [
  'cozmo',
  'capsules',
  'billes',
  'amande',
  'traits',
  'anneaux',
];
const STYLE_LABELS: Record<string, string> = {
  cozmo: 'Cozmo',
  capsules: 'Capsules',
  billes: 'Billes',
  amande: 'Amande',
  traits: 'Traits',
  anneaux: 'Anneaux',
};
const NATIVE_STYLE_GEOMETRY: Record<string, readonly [number, number, number]> = {
  cozmo: [1.3, 1.05, 0.45],
  capsules: [1, 1.4, 0.55],
  billes: [1.15, 1.15, 0.5],
  amande: [1.1, 0.85, 0.5],
  traits: [0.42, 1.1, 0.6],
  anneaux: [1.06, 1.06, 0.5],
};

export function NativeMonitor({
  style,
  values,
  size = 118,
}: {
  style: RigEyeStyleId;
  values: ChannelValues;
  size?: number;
}) {
  const [eyeW, eyeH, gap] = NATIVE_STYLE_GEOMETRY[style];
  const unit = (size * (style === 'capsules' ? 0.38 : 0.42)) / 2.6;
  const drawn = style === 'traits' || style === 'anneaux';
  return (
    <div
      style={{
        position: 'relative',
        width: size,
        height: size,
        transform: `rotate(${values.tilt * 0.3}deg) scale(${values.mass})`,
      }}
      aria-hidden="true"
    >
      <Img
        src={staticFile('avatars/monitor/v2/body.webp')}
        style={{ width: size, height: size, position: 'absolute', left: 0, top: 0 }}
      />
      <div
        style={{
          position: 'absolute',
          left: size * MONITOR_SCREEN.x,
          top: size * MONITOR_SCREEN.y,
          width: size * MONITOR_SCREEN.width,
          height: size * MONITOR_SCREEN.height,
          borderRadius: size * MONITOR_SCREEN.radius,
          background: 'linear-gradient(145deg,#dff3fc,#b8daec 50%,#8eb8d3)',
          boxShadow: 'inset 0 2px 5px rgba(31,75,99,.28)',
        }}
      />
      {(['L', 'R'] as const).map(side => {
        const left =
          size / 2 + ((side === 'L' ? -1 : 1) * (eyeW + gap) * unit) / 2 - (eyeW * unit) / 2;
        const contour = strokeContours(values, side);
        const closed = clamp(values[`blink${side}`]);
        const eyeStyle: CSSProperties = {
          position: 'absolute',
          left,
          top: size * 0.292 + values[`ty${side}`] * unit,
          width: eyeW * unit,
          height: eyeH * unit,
          transformOrigin: `50% ${values[`oy${side}`]}%`,
          transform: `rotate(${values[`baseRot${side}`] + values[`rot${side}`]}deg) scale(${values[`sx${side}`]}, ${values[`sy${side}`] * (drawn ? 1 - closed * 0.92 : 1)})`,
          clipPath: drawn
            ? undefined
            : `inset(${values[`lidTop${side}`] + closed * 50}% 0 ${values[`lidBot${side}`] + closed * 50}% 0 round 3px)`,
        };
        return (
          <React.Fragment key={side}>
            <div style={eyeStyle}>
              {drawn ? (
                <svg
                  viewBox="0 0 100 100"
                  style={{ width: '100%', height: '100%', overflow: 'visible' }}
                >
                  <path
                    d={contour.upper}
                    fill="none"
                    stroke="#2492c4"
                    strokeWidth={contour.width}
                    strokeLinecap="round"
                  />
                  <path
                    d={contour.lower}
                    fill="none"
                    stroke="#2492c4"
                    strokeWidth={contour.width}
                    strokeLinecap="round"
                    opacity={contour.lowerOpacity}
                  />
                </svg>
              ) : (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    background: 'linear-gradient(130deg,#62cdf3,#2492c4 62%,#145777)',
                    borderRadius: `${values[`rTop${side}`] * unit}px ${values[`rTop${side}`] * unit}px ${values[`rBot${side}`] * unit}px ${values[`rBot${side}`] * unit}px / ${values[`rvTop${side}`] * unit}px ${values[`rvTop${side}`] * unit}px ${values[`rvBot${side}`] * unit}px ${values[`rvBot${side}`] * unit}px`,
                  }}
                >
                  {style === 'billes' ? (
                    <div
                      style={{
                        position: 'absolute',
                        width: unit * 0.38,
                        height: unit * 0.38,
                        left: '50%',
                        top: '50%',
                        borderRadius: '50%',
                        background: '#11364d',
                        transform: `translate(calc(-50% + ${values.gazeX * unit * 0.18}px), calc(-50% + ${values.gazeY * unit * 0.12}px))`,
                      }}
                    />
                  ) : null}
                </div>
              )}
            </div>
            {!drawn ? (
              <svg
                viewBox="0 0 100 36"
                preserveAspectRatio="none"
                style={{
                  position: 'absolute',
                  left,
                  top: size * 0.245 + values[`browY${side}`] * unit,
                  width: eyeW * unit,
                  height: unit * 0.6,
                  overflow: 'visible',
                }}
              >
                <path
                  d={browPath(values, side)}
                  stroke="#1c526f"
                  strokeWidth="16"
                  strokeLinecap="round"
                  fill="none"
                />
              </svg>
            ) : null}
          </React.Fragment>
        );
      })}
      <FaceMouth
        values={values}
        sculpted={false}
        color="#21789e"
        width={unit * 0.88 * values.mouthW}
        height={unit * 0.68}
        top={size * 0.445}
      />
    </div>
  );
}

function SignalIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M5.2 5.2a9.6 9.6 0 0 0 0 13.6m13.6-13.6a9.6 9.6 0 0 1 0 13.6M8 8a5.7 5.7 0 0 0 0 8m8-8a5.7 5.7 0 0 1 0 8" />
    </svg>
  );
}

function PsychePanel({ seconds, label, mood }: { seconds: number; label: string; mood: string }) {
  const speaking = beatAt(seconds).expression === 'speaking';
  return (
    <div
      style={{
        width: 286,
        padding: '26px 23px',
        border: '1px solid rgba(164,179,224,.18)',
        borderRadius: 25,
        background: 'linear-gradient(145deg,rgba(48,54,94,.50),rgba(14,19,45,.82))',
        boxShadow: '0 20px 45px rgba(0,0,0,.12)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          fontSize: 19,
          color: VIOLET,
          fontWeight: 650,
        }}
      >
        <SignalIcon /> Une présence expressive
      </div>
      <div style={{ color: MUTED, fontSize: 17, lineHeight: 1.55, marginTop: 12 }}>
        L’activité et l’état de LIA
        <br />
        se lisent dans son visage.
      </div>
      <div
        style={{
          marginTop: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ color: MUTED, fontSize: 16 }}>État illustré</span>
        <span style={{ color: INK, fontSize: 19, fontWeight: 600 }}>{mood}</span>
      </div>
      {[
        { label: 'Curiosité', value: 0.78, color: VIOLET },
        { label: 'Engagement', value: speaking ? 0.88 : 0.69, color: CYAN },
      ].map(item => (
        <div key={item.label} style={{ marginTop: 15 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              color: MUTED,
              fontSize: 15,
              marginBottom: 8,
            }}
          >
            <span>{item.label}</span>
            <span style={{ color: item.color }}>{Math.round(item.value * 100)} %</span>
          </div>
          <div
            style={{
              height: 5,
              borderRadius: 10,
              background: 'rgba(177,192,228,.12)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${item.value * 100}%`,
                borderRadius: 10,
                background: item.color,
              }}
            />
          </div>
        </div>
      ))}
      <div
        style={{
          borderTop: '1px solid rgba(164,179,224,.15)',
          marginTop: 23,
          paddingTop: 18,
          display: 'flex',
          alignItems: 'center',
          gap: 14,
        }}
      >
        <div style={{ height: 28, display: 'flex', gap: 3, alignItems: 'center' }}>
          {Array.from({ length: 9 }, (_, index) => (
            <div
              key={index}
              style={{
                width: 3,
                borderRadius: 4,
                background: speaking ? CYAN : VIOLET,
                height: speaking ? 5 + Math.abs(Math.sin(seconds * 11 + index * 1.7)) * 20 : 4,
                opacity: speaking ? 1 : 0.45,
              }}
            />
          ))}
        </div>
        <div style={{ fontSize: 17, color: INK }}>{label}</div>
      </div>
    </div>
  );
}

/** Dedicated avatar focus. The composition supplies local scene time in frames. */
export function AvatarShowcase({ frame: suppliedFrame }: { frame?: number }) {
  const currentFrame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frame = Math.max(0, suppliedFrame ?? currentFrame);
  const cycleFrame = frame % Math.round(CYCLE_SECONDS * fps);
  const seconds = cycleFrame / fps;
  const rigs = useMemo(
    () =>
      ({
        billes: sampleNativeRig('billes', fps),
        smiley: sampleNativeRig('smiley', fps),
        ...Object.fromEntries(
          MONITOR_STYLES.filter(style => style !== 'billes').map(style => [
            style,
            sampleNativeRig(style, fps),
          ])
        ),
      }) as Record<RigEyeStyleId, ChannelValues[]>,
    [fps]
  );
  const values = rigs.billes[cycleFrame];
  const smileyValues = rigs.smiley[cycleFrame];
  const beat = beatAt(seconds);
  const characters: readonly Character[] = [
    'spirit',
    'moss',
    'lumen',
    'nimbo',
    'orbit',
    'boulon',
    'oscar',
  ];
  const monitorPage = seconds >= 8;
  const pageEntrance = clamp((seconds - (monitorPage ? 8 : 0)) / 0.5);
  const pageExit = monitorPage ? 1 : clamp((8 - seconds) / 0.5);
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: 700,
        color: INK,
        border: '1px solid rgba(151,173,221,.2)',
        borderRadius: 32,
        overflow: 'hidden',
        background:
          'radial-gradient(ellipse at 22% 42%,rgba(70,80,185,.18),transparent 44%),radial-gradient(ellipse at 60% 18%,rgba(65,192,230,.09),transparent 43%),linear-gradient(145deg,rgba(20,29,58,.92),rgba(10,15,35,.94))',
        boxShadow: '0 26px 70px rgba(0,0,0,.25)',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 32,
          left: 34,
          right: 34,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ fontSize: 15, letterSpacing: 3.5, color: CYAN, fontWeight: 700 }}>
            AVATARS ANIMÉS
          </div>
          <div style={{ fontSize: 27, marginTop: 8, fontWeight: 650, letterSpacing: -0.5 }}>
            Choisis sa présence.
          </div>
        </div>
        <div
          style={{
            border: '1px solid rgba(159,147,229,.3)',
            borderRadius: 99,
            padding: '9px 15px',
            fontSize: 16,
            color: VIOLET,
          }}
        >
          Personnalité · expressions · voix
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          left: 25,
          top: 143,
          width: 290,
          height: 320,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <div
          style={{
            position: 'absolute',
            width: 218,
            height: 45,
            top: 227,
            borderRadius: '50%',
            background: 'radial-gradient(ellipse,rgba(70,132,209,.20),transparent 69%)',
            transform: `scale(${values.mass})`,
          }}
        />
        <NativeAvatar kind="bip" variant="male" size={248} values={values} />
        <div style={{ marginTop: 23, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 19, fontWeight: 650 }}>BIP</span>
          <span
            style={{
              fontSize: 14,
              color: CYAN,
              border: '1px solid rgba(104,206,239,.25)',
              borderRadius: 99,
              padding: '5px 10px',
            }}
          >
            Compagnon
          </span>
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          left: 340,
          top: 160,
          width: 280,
          height: 303,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <div
          style={{
            position: 'absolute',
            width: 203,
            height: 36,
            top: 221,
            borderRadius: '50%',
            background: 'radial-gradient(ellipse,rgba(238,174,80,.17),transparent 69%)',
          }}
        />
        <NativeAvatar kind="smiley" size={222} values={smileyValues} />
        <div style={{ fontSize: 19, marginTop: 29, fontWeight: 650 }}>Smiley</div>
      </div>
      <div style={{ position: 'absolute', right: 31, top: 133 }}>
        <PsychePanel seconds={seconds} label={beat.label} mood={beat.mood} />
      </div>
      <div style={{ position: 'absolute', left: 34, right: 34, top: 482 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: 16,
            color: MUTED,
          }}
        >
          <span>
            {monitorPage ? 'Six langages de regard' : 'Des personnages pour ton compagnon'}
          </span>
          <div style={{ display: 'flex', gap: 5 }}>
            {[false, true].map(page => (
              <span
                key={String(page)}
                style={{
                  width: page === monitorPage ? 22 : 7,
                  height: 5,
                  borderRadius: 8,
                  background: page === monitorPage ? CYAN : 'rgba(177,192,228,.22)',
                }}
              />
            ))}
          </div>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-around',
            marginTop: 17,
            opacity: pageEntrance * pageExit,
            transform: `translateY(${(1 - pageEntrance) * 14}px)`,
          }}
        >
          {monitorPage
            ? MONITOR_STYLES.map(style => (
                <div
                  key={style}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    width: 130,
                  }}
                >
                  <NativeMonitor style={style} values={rigs[style][cycleFrame]} size={104} />
                  <span style={{ fontSize: 16, color: '#d3d9ed', marginTop: 1 }}>
                    {STYLE_LABELS[style]}
                  </span>
                </div>
              ))
            : characters.map((character, index) => (
                <div
                  key={character}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    width: 111,
                    transform: `translateY(${Math.sin(seconds * 1.1 + index * 0.5) * 2}px)`,
                  }}
                >
                  <NativeAvatar
                    kind={character}
                    size={90}
                    values={resolvePose('neutral', 'billes')}
                  />
                  <span style={{ fontSize: 16, color: '#d3d9ed', marginTop: 10 }}>
                    {character[0].toUpperCase() + character.slice(1)}
                  </span>
                </div>
              ))}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: 45,
          padding: '0 34px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderTop: '1px solid rgba(164,179,224,.13)',
          background: 'rgba(13,17,36,.7)',
          fontSize: 14,
          color: MUTED,
        }}
      >
        <span>
          <span style={{ color: VIOLET }}>Avatar vidéo Simli</span> · optionnel · expérimental
        </span>
        <span>Compte fournisseur personnel</span>
      </div>
    </div>
  );
}

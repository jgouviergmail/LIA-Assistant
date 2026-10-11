/** Worn props use the same native surface projection; CSS retains existing one-shot motion. */
import { restChannelValues, type ChannelValues } from '../rig/channels';
import { projectSmileySurface, spherePose } from '../smiley/sphere-geometry';
import { bodyVolumeMaterial } from './volume-binding';
import {
  VOLUME_CHARACTERS,
  projectVolumeSurface,
  volumePose,
  volumeProfile,
  type VolumeCharacter,
  type VolumeProfile,
} from './volume-geometry';
type Kind = 'crown' | 'tear' | 'sweat' | 'heat';
const KINDS = ['crown', 'tear', 'sweat', 'heat'] as const;
const NEUTRAL = restChannelValues();
const format = (value: number) => String(Number(value.toFixed(4)));
const finite = (value: number) => (Number.isFinite(value) ? value : 0);
const bounded = (value: number, limit: number) => Math.max(-limit, Math.min(limit, finite(value)));
function numeric(style: CSSStyleDeclaration, key: string, fallback: number) {
  const value = parseFloat(style.getPropertyValue(key));
  return Number.isFinite(value) ? value : fallback;
}
function propFrame(root: HTMLElement, profile: VolumeProfile | null) {
  const style = getComputedStyle(root),
    scale = numeric(style, '--avatar-accessory-scale', 1);
  const eyeScale =
    profile?.character === 'monitor' ? numeric(style, '--monitor-face-scale', 0.42) : 1;
  const half =
    (numeric(style, '--eye-w', 0.59265) + numeric(style, '--eye-gap', 0.01912) / 2) * eyeScale;
  const faceY = (numeric(style, '--avatar-face-y', 52.405) / 100 - 0.5) * 2.6;
  const crownY = (numeric(style, '--avatar-crown-y', 0) / 100 - 0.5) * 2.6;
  return {
    eyeScale,
    monitor: profile?.character === 'monitor',
    human: profile?.character === 'oscar',
    smiley: root.dataset.style === 'smiley',
    anchors: {
      crown: { x: 0, y: Math.min(crownY - 0.24 * scale, faceY - 1.25 * scale) + 0.8 * scale },
      tear: { x: -half - 0.02 + 0.1 * scale, y: faceY + 0.13 * scale },
      sweat: { x: half + 0.1 - 0.09 * scale, y: faceY - 0.3 * scale },
      heat: { x: half - 0.05 * scale, y: faceY - 0.175 * scale },
    },
  };
}
type Frame = ReturnType<typeof propFrame>;
function eyeTravel(frame: Frame, kind: Kind, values: Readonly<ChannelValues>) {
  if (kind === 'crown' || frame.human) return { x: 0, y: 0 };
  const side = kind === 'tear' ? 'L' : 'R';
  if (frame.monitor)
    return {
      x:
        (finite(values.gazeX) * 0.09 +
          finite(values.headYaw) * 0.12 +
          finite(values[`tx${side}`])) *
        frame.eyeScale,
      y:
        (finite(values.gazeY) * 0.07 +
          finite(values.headPitch) * 0.07 +
          finite(values[`ty${side}`])) *
        frame.eyeScale,
    };
  if (frame.smiley)
    return {
      x: finite(values.gazeX) * 0.065 + finite(values[`tx${side}`]),
      y: finite(values.gazeY) * 0.045 + finite(values[`ty${side}`]),
    };
  return {
    x: finite(values.gazeX) * 0.03 + bounded(values[`tx${side}`], 0.08),
    y: finite(values.gazeY) * 0.02 + bounded(values[`ty${side}`], 0.1),
  };
}
function propTransform(
  kind: Kind,
  frame: Frame,
  profile: VolumeProfile | null,
  values: Readonly<ChannelValues>
) {
  const rest = frame.anchors[kind],
    shift = eyeTravel(frame, kind, values),
    point = { x: rest.x + shift.x, y: rest.y + shift.y };
  const current = project(frame, profile, point, values),
    neutral = project(frame, profile, rest, NEUTRAL);
  const x = current.x - neutral.x,
    y = current.y - neutral.y;
  return `translate(${format(x)}em, ${format(y)}em) matrix(${[current.a, current.b, current.c, current.d].map(format).join(', ')}, 0, 0)`;
}
function project(
  frame: Frame,
  profile: VolumeProfile | null,
  point: { x: number; y: number },
  values: Readonly<ChannelValues>
) {
  if (frame.smiley) return projectSmileySurface(point, spherePose(values));
  const surface = profile!;
  return projectVolumeSurface(surface, point, volumePose(values, surface.character));
}
function sourceProfile(root: HTMLElement) {
  const character = root.dataset.volumeCharacter;
  if (!VOLUME_CHARACTERS.includes(character as VolumeCharacter)) return null;
  return volumeProfile(
    character as VolumeCharacter,
    root.dataset.volumeVariant === 'female' ? 'female' : 'male'
  );
}
export function createPhysicalPropWriter(root: HTMLElement) {
  let key = '',
    profile: VolumeProfile | null = null,
    frame: Frame | null = null;
  const previous = new Map<Kind, string>();
  const clear = () => {
    for (const kind of KINDS)
      if (previous.has(kind)) root.style.removeProperty(`--volume-${kind}-transform`);
    previous.clear();
  };
  return {
    write(values: Readonly<ChannelValues>) {
      const current = `${root.dataset.style}-${root.dataset.volumeCharacter}-${root.dataset.volumeVariant}-${root.dataset.smileyVariant}`;
      if (current !== key) {
        clear();
        key = current;
        profile = sourceProfile(root);
        frame = propFrame(root, profile);
      }
      if (!frame?.smiley && (!profile || root.dataset.volumeReady !== 'true')) {
        clear();
        return;
      }
      profile = bodyVolumeMaterial(root)?.profile ?? profile;
      for (const kind of KINDS) {
        const text = propTransform(kind, frame!, profile, values);
        if (text === previous.get(kind)) continue;
        root.style.setProperty(`--volume-${kind}-transform`, text);
        previous.set(kind, text);
      }
    },
    reset() {
      clear();
      key = '';
    },
    dispose() {
      clear();
      frame = null;
      profile = null;
    },
  };
}

/** Facial materials are tangent patches of the body, painted by the sole native writer. */
import type { ChannelValues } from '../rig/channels';
import {
  bindVolumeProjection,
  bodyVolumeMaterial,
  paintBodyVolume,
  resetBodyVolume,
} from './volume-binding';
import {
  VOLUME_CHARACTERS,
  projectEyeSocket,
  projectVolumeSurface,
  volumePose,
  volumeProfile,
  type VolumeCharacter,
  type VolumeProfile,
} from './volume-geometry';
import { volumeFaceContour } from './volume-mask';
import { createPhysicalPropWriter } from './physical-prop-writer';

const format = (value: number) => String(Number(value.toFixed(4)));
const finite = (value: number) => (Number.isFinite(value) ? value : 0);
const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, finite(value)));
function number(style: CSSStyleDeclaration, key: string, fallback: number) {
  const value = parseFloat(style.getPropertyValue(key));
  return Number.isFinite(value) ? value : fallback;
}
function framing(root: HTMLElement, profile: VolumeProfile) {
  const style = getComputedStyle(root);
  return {
    eyeX: (number(style, '--eye-w', 0.59265) + number(style, '--eye-gap', 0.01912)) / 2,
    eyeY: (number(style, '--companion-eye-y', 52.405) / 100 - 0.5) * 2.6,
    mouthY: (number(style, '--companion-mouth-y', 65.43) / 100 - 0.5) * 2.6,
    screenY:
      (number(style, '--screen-top', 22.2807) / 100 +
        number(style, '--screen-height', 38.5965) / 200 -
        0.5) *
      2.6,
    monitor: profile.character === 'monitor',
  };
}
type Framing = ReturnType<typeof framing>;

function facialTransform(
  kind: string,
  values: Readonly<ChannelValues>,
  frame: Framing,
  profile: VolumeProfile
) {
  const mouth = kind === 'mouth',
    side = kind === 'left' ? 'L' : 'R',
    human = profile.character === 'oscar';
  const rest = {
    x: mouth ? 0 : side === 'L' ? -frame.eyeX : frame.eyeX,
    y: mouth ? frame.mouthY : frame.eyeY,
  };
  const gaze = human
    ? { x: 0, y: 0 }
    : { x: finite(values.gazeX) * 0.03, y: finite(values.gazeY) * 0.02 };
  const shift = mouth
    ? { x: finite(values.mouthX), y: finite(values.mouthY) + finite(values.mouthOpen) * 0.035 }
    : human
      ? { x: 0, y: 0 }
      : { x: clamp(values[`tx${side}`], 0.08), y: clamp(values[`ty${side}`], 0.1) };
  const project = human && !mouth ? projectEyeSocket : projectVolumeSurface;
  const projected = project(
    profile,
    { x: rest.x + gaze.x + shift.x, y: rest.y + gaze.y + shift.y },
    volumePose(values, profile.character)
  );
  const x = projected.x - rest.x - gaze.x - projected.a * shift.x - projected.c * shift.y;
  const y = projected.y - rest.y - gaze.y - projected.b * shift.x - projected.d * shift.y;
  return `translate(${format(x)}em, ${format(y)}em) matrix(${[projected.a, projected.b, projected.c, projected.d].map(format).join(', ')}, 0, 0)`;
}

function monitorTransform(values: Readonly<ChannelValues>, frame: Framing, profile: VolumeProfile) {
  const point = projectVolumeSurface(
    profile,
    { x: 0, y: frame.screenY },
    volumePose(values, 'monitor')
  );
  return `translate(${format(point.x)}em, ${format(point.y - frame.screenY)}em) matrix(${[point.a, point.b, point.c, point.d].map(format).join(', ')}, 0, 0)`;
}

export function createVolumeSurfaceWriter(root: HTMLElement) {
  const props = createPhysicalPropWriter(root);
  let appearance = '',
    profile: VolumeProfile | null = null,
    frame: Framing | null = null;
  let organs: { element: HTMLElement; kind: string; previous: string }[] = [];
  let contour: ReturnType<typeof volumeFaceContour> | null = null,
    contourMask: object | undefined,
    clip = '';
  let clipYaw = NaN,
    clipPitch = NaN,
    painted = false;
  const clear = () => {
    if (!painted && !clip) return;
    for (const organ of organs) {
      organ.element.style.removeProperty('transform');
      organ.element.style.removeProperty('transform-origin');
      organ.previous = '';
    }
    root.style.removeProperty('--volume-face-clip');
    clip = '';
    clipYaw = clipPitch = NaN;
    painted = false;
  };
  const acquire = () => {
    const current = `${root.dataset.style}-${root.dataset.volumeCharacter}-${root.dataset.volumeVariant}`;
    if (current === appearance) return;
    clear();
    appearance = current;
    contour = null;
    contourMask = undefined;
    const character = root.dataset.volumeCharacter;
    if (!VOLUME_CHARACTERS.includes(character as VolumeCharacter)) {
      profile = null;
      frame = null;
      organs = [];
      return;
    }
    profile = volumeProfile(
      character as VolumeCharacter,
      root.dataset.volumeVariant === 'female' ? 'female' : 'male'
    );
    frame = framing(root, profile);
    const selector = frame.monitor
      ? '.lia-monitor-screen, .lia-monitor-brows'
      : '[data-volume-surface]';
    organs = [...root.querySelectorAll<HTMLElement>(selector)].map(element => ({
      element,
      kind: element.dataset.volumeSurface ?? 'screen',
      previous: '',
    }));
  };
  const writeProjection = (values: Readonly<ChannelValues>) => {
    props.write(values);
    acquire();
    if (!profile || !frame || root.dataset.volumeReady !== 'true') {
      clear();
      return;
    }
    const material = bodyVolumeMaterial(root);
    if (material) profile = material.profile;
    if (material && material.mask !== contourMask && !frame.monitor) {
      contourMask = material.mask;
      contour = volumeFaceContour(material.mask, profile, frame.eyeY);
      clipYaw = clipPitch = NaN;
    }
    if (contour) {
      const pose = volumePose(values, profile.character);
      if (pose.yaw !== clipYaw || pose.pitch !== clipPitch) {
        clipYaw = pose.yaw;
        clipPitch = pose.pitch;
        const current = `polygon(${contour
          .map(point => {
            const p = projectVolumeSurface(profile!, point, pose);
            return `${format((p.x / 2.6 + 0.5) * 100)}% ${format((p.y / 2.6 + 0.5) * 100)}%`;
          })
          .join(', ')})`;
        if (current !== clip) {
          root.style.setProperty('--volume-face-clip', current);
          clip = current;
        }
      }
    }
    writeOrgans(values, profile, frame);
  };
  const writeOrgans = (values: Readonly<ChannelValues>, profile: VolumeProfile, frame: Framing) => {
    for (const organ of organs) {
      const text = frame.monitor
        ? monitorTransform(values, frame, profile)
        : facialTransform(organ.kind, values, frame, profile);
      if (text === organ.previous) continue;
      organ.element.style.transformOrigin =
        organ.kind === 'mouth' ? `50% ${format((frame.mouthY / 2.6 + 0.5) * 100)}%` : '50% 50%';
      organ.element.style.transform = text;
      organ.previous = text;
      painted = true;
    }
  };
  const unbind = bindVolumeProjection(root, writeProjection);
  return {
    write(values: Readonly<ChannelValues>) {
      paintBodyVolume(root, values);
      writeProjection(values);
    },
    reset() {
      props.reset();
      appearance = '';
      resetBodyVolume(root);
    },
    dispose() {
      props.dispose();
      unbind();
      clear();
      organs = [];
      profile = null;
    },
  };
}

/** Source-space influences are prepared once, never resampled by the frame writer. */
import { LIMB_CHANNELS, type ChannelValues } from '../rig/channels';
import { limbProfile, type LimbChain, type LimbJoint } from './limb-profiles';
import type { VolumeMesh, VolumeProfile, VolumeSkin } from './volume-geometry';

function smooth(value: number): number {
  const t = Math.max(0, Math.min(1, value));
  return t * t * (3 - 2 * t);
}
function weight(joint: LimbJoint | null, chain: LimbChain, u: number, v: number): number {
  if (!joint) return 0;
  const [x0, y0, x1, y1] = chain.region;
  const distance =
    (u - joint.pivot[0]) * joint.direction[0] + (v - joint.pivot[1]) * joint.direction[1];
  return (
    smooth(distance / joint.blend) *
    smooth((u - x0) / chain.feather) *
    smooth((x1 - u) / chain.feather) *
    smooth((v - y0) / chain.feather) *
    smooth((y1 - v) / chain.feather)
  );
}
/** The same spatial weights apply to front, back, contour and fine alpha detail. */
export function limbInfluence(
  chains: readonly LimbChain[],
  u: number,
  v: number,
  scale: number
): readonly number[] {
  const chain = chains.find(({ region: [x0, y0, x1, y1] }) => u > x0 && u < x1 && v > y0 && v < y1);
  if (!chain) return [0, 0, 0, 0, 0, 0, 0, 0];
  const derivative = (joint: LimbJoint | null, du: number, dv: number) =>
    (weight(joint, chain, u + du, v + dv) - weight(joint, chain, u - du, v - dv)) /
    (0.00002 * 2.6 * scale);
  return [
    chain.parent ? LIMB_CHANNELS.indexOf(chain.parent.channel) : 0,
    chain.distal ? LIMB_CHANNELS.indexOf(chain.distal.channel) : 0,
    weight(chain.parent, chain, u, v),
    weight(chain.distal, chain, u, v),
    derivative(chain.parent, 0.00001, 0),
    derivative(chain.parent, 0, 0.00001),
    derivative(chain.distal, 0.00001, 0),
    derivative(chain.distal, 0, 0.00001),
  ];
}

export function withLimbSkin(mesh: VolumeMesh, profile: VolumeProfile): VolumeMesh {
  const chains = limbProfile(profile.character, profile.variant);
  if (!chains.length) return mesh;
  const skin: VolumeSkin = {
    vertices: new Float32Array(mesh.vertices.length),
    joints: new Float32Array(LIMB_CHANNELS.length * 4),
    limits: new Float32Array(LIMB_CHANNELS.length),
  };
  for (const chain of chains)
    for (const joint of [chain.parent, chain.distal]) {
      if (!joint) continue;
      const index = LIMB_CHANNELS.indexOf(joint.channel);
      skin.joints[index * 4] = (joint.pivot[0] - 0.5) * 2.6 * profile.scale;
      skin.joints[index * 4 + 1] = (joint.pivot[1] - 0.5) * 2.6 * profile.scale;
      skin.limits[index] = joint.limit;
    }
  for (let offset = 0; offset < mesh.vertices.length; offset += 8) {
    // Positions, not UVs: opaque side walls can sample a nearby pigment texel.
    const u = mesh.vertices[offset] / (2.6 * profile.scale) + 0.5;
    const v = mesh.vertices[offset + 1] / (2.6 * profile.scale) + 0.5;
    skin.vertices.set(limbInfluence(chains, u, v, profile.scale), offset);
  }
  return { ...mesh, skin };
}

/** Clamp every offered joint to the anatomical limit; malformed channels are neutral. */
export function updateLimbUniforms(skin: VolumeSkin, values?: Readonly<ChannelValues>): void {
  for (let index = 0; index < LIMB_CHANNELS.length; index++) {
    const offered = values?.[LIMB_CHANNELS[index]] ?? 0;
    skin.joints[index * 4 + 2] = Number.isFinite(offered)
      ? (Math.max(-skin.limits[index], Math.min(skin.limits[index], offered)) * Math.PI) / 180
      : 0;
  }
}

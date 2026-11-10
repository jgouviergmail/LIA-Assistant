import { describe, expect, it } from 'vitest';
import { LIMB_CHANNELS, restChannelValues } from '../../rig/channels';
import { limbProfile, type LimbChain } from '../limb-profiles';
import { limbInfluence, updateLimbUniforms, withLimbSkin } from '../limb-skin';
import {
  VOLUME_CHARACTERS,
  VOLUME_BUFFER_MAX,
  VOLUME_EXTENT,
  visibleVolumeMesh,
  volumeProfile,
  type VolumeSkin,
} from '../volume-geometry';
import { bodySurfaceProfile } from '../volume-distance';
import sourceAlpha from './fixtures/limb-source-alpha.json';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { inflateSync } from 'node:zlib';

/** Independent mathematical consumer of the GPU port's joint/weight data. */
function displaced(
  chains: readonly LimbChain[],
  skin: VolumeSkin,
  u: number,
  v: number,
  scale: number
) {
  const weights = limbInfluence(chains, u, v, scale);
  let x = (u - 0.5) * 2.6 * scale,
    y = (v - 0.5) * 2.6 * scale;
  for (const [joint, weight] of [
    [weights[1], weights[3]],
    [weights[0], weights[2]],
  ]) {
    const px = skin.joints[joint * 4],
      py = skin.joints[joint * 4 + 1];
    const angle = skin.joints[joint * 4 + 2] * weight;
    const dx = x - px,
      dy = y - py;
    x = px + Math.cos(angle) * dx - Math.sin(angle) * dy;
    y = py + Math.sin(angle) * dx + Math.cos(angle) * dy;
  }
  return [x, y];
}

describe('the encoded articulation remains attached and orientation preserving', () => {
  it.each(VOLUME_CHARACTERS)(
    '%s has no painted fold or collapsed normal transform at either anatomical limit',
    character => {
      for (const variant of ['female', 'male'] as const) {
        const profile = volumeProfile(character, variant),
          chains = limbProfile(character, variant);
        const skin = withLimbSkin(
          { vertices: new Float32Array(), indices: new Uint16Array() },
          profile
        ).skin;
        if (!skin) continue;
        const source = sourceAlpha[`${character}/${variant}` as keyof typeof sourceAlpha];
        expect(
          createHash('sha256')
            .update(readFileSync(join(process.cwd(), 'public', source.asset)))
            .digest('hex')
        ).toBe(source.sha256);
        const alpha = inflateSync(Buffer.from(source.alphaZlib, 'base64'));
        expect(alpha.length).toBe(source.width * source.height);
        for (const parentSign of [-1, 0, 1])
          for (const distalSign of [-1, 0, 1]) {
            const values = restChannelValues();
            for (const channel of LIMB_CHANNELS)
              values[channel] =
                (channel.startsWith('wrist') || channel.startsWith('foot')
                  ? distalSign
                  : parentSign) * 999;
            updateLimbUniforms(skin, values);
            let minimum = Infinity,
              at = '';
            for (let row = 0; row < source.height; row++)
              for (let col = 0; col < source.width; col++) {
                // Published WebP has a flat alpha=2 quantization floor across the empty canvas.
                // Cover physical pixels and visible hair/shadow, not that nominally empty plane.
                if (alpha[row * source.width + col] < 16) continue;
                const u = (col + 0.5) / source.width,
                  v = (row + 0.5) / source.height;
                const h = 0.000002;
                const left = displaced(chains, skin, u - h, v, profile.scale),
                  right = displaced(chains, skin, u + h, v, profile.scale);
                const top = displaced(chains, skin, u, v - h, profile.scale),
                  bottom = displaced(chains, skin, u, v + h, profile.scale);
                const divisor = 2 * h * 2.6 * profile.scale;
                const dx = [(right[0] - left[0]) / divisor, (right[1] - left[1]) / divisor];
                const dy = [(bottom[0] - top[0]) / divisor, (bottom[1] - top[1]) / divisor];
                const determinant = dx[0] * dy[1] - dx[1] * dy[0];
                if (determinant < minimum) {
                  minimum = determinant;
                  at = `${u.toFixed(4)},${v.toFixed(4)}`;
                }
              }
            expect(
              minimum,
              `${character}/${variant} signs ${parentSign}/${distalSign} at ${at}`
            ).toBeGreaterThan(0.15);
          }
      }
    }
  );

  it.each(VOLUME_CHARACTERS)(
    '%s preserves every raster-significant physical triangle at all joint extremes',
    character => {
      for (const variant of ['female', 'male'] as const) {
        if (!limbProfile(character, variant).length) continue;
        const source = sourceAlpha[`${character}/${variant}` as keyof typeof sourceAlpha];
        const mask = {
          width: source.width,
          height: source.height,
          alpha: new Uint8Array(inflateSync(Buffer.from(source.alphaZlib, 'base64'))),
        };
        const profile = bodySurfaceProfile(volumeProfile(character, variant), mask);
        const mesh = withLimbSkin(visibleVolumeMesh(profile, mask), profile),
          skin = mesh.skin!;
        const transformed = new Float64Array(mesh.vertices.length / 4);
        for (const parentSign of [-1, 0, 1])
          for (const distalSign of [-1, 0, 1]) {
            const values = restChannelValues();
            for (const channel of LIMB_CHANNELS)
              values[channel] =
                (channel.startsWith('wrist') || channel.startsWith('foot')
                  ? distalSign
                  : parentSign) * 999;
            updateLimbUniforms(skin, values);
            for (let offset = 0; offset < mesh.vertices.length; offset += 8) {
              let x = mesh.vertices[offset],
                y = mesh.vertices[offset + 1];
              for (const [joint, weight] of [
                [skin.vertices[offset + 1], skin.vertices[offset + 3]],
                [skin.vertices[offset], skin.vertices[offset + 2]],
              ]) {
                const px = skin.joints[joint * 4],
                  py = skin.joints[joint * 4 + 1],
                  angle = skin.joints[joint * 4 + 2] * weight;
                const dx = x - px,
                  dy = y - py;
                x = px + Math.cos(angle) * dx - Math.sin(angle) * dy;
                y = py + Math.sin(angle) * dx + Math.cos(angle) * dy;
              }
              transformed[offset / 4] = x;
              transformed[offset / 4 + 1] = y;
            }
            let minimumPixels = Infinity,
              significantMinimum = Infinity,
              at = '';
            const area = (
              vertices: Float32Array | Float64Array,
              stride: number,
              a: number,
              b: number,
              c: number
            ) =>
              (vertices[b * stride] - vertices[a * stride]) *
                (vertices[c * stride + 1] - vertices[a * stride + 1]) -
              (vertices[b * stride + 1] - vertices[a * stride + 1]) *
                (vertices[c * stride] - vertices[a * stride]);
            for (let index = 0; index < mesh.indices.length; index += 3) {
              const a = mesh.indices[index],
                b = mesh.indices[index + 1],
                c = mesh.indices[index + 2];
              const original = area(mesh.vertices, 8, a, b, c);
              // BodyVolume's largest drawing buffer spans 192 pixels over 3.4 model units.
              // Almost-collinear contour cuts can reverse by less than .1 pixel². The
              // uncullled native material retains them; relative area is ill-conditioned
              // there. Every triangle resolving beyond that absolute budget must keep
              // its winding, in both its original and articulated footprint.
              const pixelsPerDoubleArea = 0.5 * (VOLUME_BUFFER_MAX / (VOLUME_EXTENT * 2)) ** 2;
              const originalPixels = Math.abs(original) * pixelsPerDoubleArea;
              const projectedPixels =
                area(transformed, 2, a, b, c) * Math.sign(original) * pixelsPerDoubleArea;
              if (
                Math.max(originalPixels, Math.abs(projectedPixels)) >= 0.1 &&
                projectedPixels < significantMinimum
              ) {
                significantMinimum = projectedPixels;
                at =
                  [a, b, c]
                    .map(
                      vertex =>
                        `${mesh.vertices[vertex * 8 + 6].toFixed(5)},${mesh.vertices[vertex * 8 + 7].toFixed(5)}`
                    )
                    .join(' / ') + ` original ${originalPixels}`;
              }
              minimumPixels = Math.min(minimumPixels, projectedPixels);
            }
            expect(
              minimumPixels,
              `${character}/${variant} triangle signs ${parentSign}/${distalSign}`
            ).toBeGreaterThan(-0.1);
            expect(
              significantMinimum,
              `${character}/${variant} ${parentSign}/${distalSign}: ${at}`
            ).toBeGreaterThan(0);
          }
      }
    }
  );
});

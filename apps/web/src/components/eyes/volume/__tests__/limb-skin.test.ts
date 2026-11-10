import { describe, expect, it } from 'vitest';
import { LIMB_CHANNELS, restChannelValues } from '../../rig/channels';
import { limbProfile, type LimbChain } from '../limb-profiles';
import { limbInfluence, updateLimbUniforms, withLimbSkin } from '../limb-skin';
import { VOLUME_CHARACTERS, volumeProfile, type VolumeMesh } from '../volume-geometry';
import { withSoftFringe } from '../volume-fringe';
import { createMeshGpu } from '../mesh-gpu';
import { volumeGraphics } from '../../__tests__/volume-graphics';
import { hasLimb } from '../../rig/limbs';

const empty = (): VolumeMesh => ({ vertices: new Float32Array(), indices: new Uint16Array() });
const variants = ['female', 'male'] as const;
// Hand-located distal landmarks on the published 192px source pictures, not profile-derived.
const landmarks = [
  ['spirit', [0.19, 0.66], [0.11, 0.64]],
  ['moss', [0.19, 0.68], [0.115, 0.65]],
  ['lumen', [0.19, 0.66], [0.12, 0.67]],
  ['nimbo', [0.16, 0.72], [0.15, 0.72]],
  ['bip', [0.3, 0.79], [0.25, 0.78]],
  ['boulon', [0.18, 0.77], [0.11, 0.76]],
  ['oscar', [0.33, 0.81], [0.29, 0.83]],
] as const;

describe('anatomical skin follows the drawn appendages, with rigid central landmarks', () => {
  it('keeps the rig capability vocabulary and the rendered anatomy in agreement', () => {
    for (const character of VOLUME_CHARACTERS)
      for (const variant of variants) {
        const skin = withLimbSkin(empty(), volumeProfile(character, variant)).skin;
        for (const [index, channel] of LIMB_CHANNELS.entries())
          expect(Boolean(skin?.limits[index]), `${character}/${variant}/${channel}`).toBe(
            hasLimb(character === 'monitor' ? 'cozmo' : character, channel)
          );
      }
  });
  it.each(landmarks)(
    '%s gives each visible left and right tip independent arm influence',
    (character, female, male) => {
      for (const [variant, point] of [
        ['female', female],
        ['male', male],
      ] as const) {
        const profile = limbProfile(character, variant);
        const left = limbInfluence(profile, point[0], point[1], 1.13);
        const right = limbInfluence(profile, 1 - point[0], point[1], 1.13);
        expect(left[0]).toBe(LIMB_CHANNELS.indexOf('armL'));
        expect(right[0]).toBe(LIMB_CHANNELS.indexOf('armR'));
        expect(left[2]).toBeGreaterThan(0.5);
        expect(right[2]).toBeCloseTo(left[2], 6);
      }
    }
  );

  it.each(VOLUME_CHARACTERS)(
    '%s leaves face, central torso and collar landmarks fixed in both variants',
    character => {
      for (const variant of variants) {
        const profile = limbProfile(character, variant);
        for (const [u, v] of [
          [0.5, 0.3],
          [0.45, 0.45],
          [0.55, 0.45],
          [0.5, 0.6],
          [0.5, 0.75],
        ]) {
          const influence = limbInfluence(profile, u, v, 1.13);
          expect(influence.slice(2)).toEqual([0, 0, 0, 0, 0, 0]);
        }
      }
    }
  );

  it.each(['orbit', 'monitor'] as const)(
    '%s stays rigid over its entire silhouette and needs no skin buffer',
    character => {
      for (const variant of variants) {
        const profile = volumeProfile(character, variant),
          mesh = withSoftFringe(empty(), profile);
        expect(withLimbSkin(mesh, profile)).toBe(mesh);
        expect(mesh.vertices.length / 8).toBe(4);
        for (let u = 0; u <= 1; u += 0.05)
          for (let v = 0; v <= 1; v += 0.05)
            expect(
              limbInfluence(limbProfile(character, variant), u, v, profile.scale).slice(2)
            ).toEqual([0, 0, 0, 0, 0, 0]);
      }
    }
  );

  it('does not infer wrists or legs from soft blobs, while all drawn feet have influence', () => {
    for (const character of ['spirit', 'nimbo', 'moss', 'lumen'] as const)
      for (const variant of variants) {
        const profile = volumeProfile(character, variant);
        const skin = withLimbSkin(empty(), profile).skin!;
        expect(skin.limits[2]).toBe(0);
        expect(skin.limits[3]).toBe(0);
        expect(skin.limits[4]).toBe(0);
        expect(skin.limits[5]).toBe(0);
        if (character === 'spirit' || character === 'nimbo') {
          expect(skin.limits[6]).toBe(0);
          expect(skin.limits[7]).toBe(0);
        }
      }
    for (const [character, female, male] of [
      ['moss', [0.39, 0.925], [0.345, 0.9]],
      ['lumen', [0.385, 0.9], [0.36, 0.9]],
      ['bip', [0.4, 0.925], [0.39, 0.88]],
      ['boulon', [0.35, 0.915], [0.285, 0.9]],
      ['oscar', [0.44, 0.965], [0.42, 0.965]],
    ] as const)
      for (const [variant, point] of [
        ['female', female],
        ['male', male],
      ] as const) {
        const profile = limbProfile(character, variant);
        expect(limbInfluence(profile, point[0], point[1], 1.13)[3]).toBeGreaterThan(0.5);
        expect(limbInfluence(profile, 1 - point[0], point[1], 1.13)[3]).toBeGreaterThan(0.5);
      }
  });

  it('encodes a smooth fixed attachment, full distal rotation and spatial derivatives in model units', () => {
    const chain: LimbChain = {
      parent: { channel: 'armL', pivot: [0.25, 0.25], direction: [0, 1], blend: 0.2, limit: 20 },
      distal: null,
      region: [0, 0, 0.5, 1],
      feather: 0.02,
    };
    expect(limbInfluence([chain], 0.25, 0.25, 1)[2]).toBe(0);
    const midway = limbInfluence([chain], 0.25, 0.35, 1);
    expect(midway[2]).toBeCloseTo(0.5, 10);
    expect(midway[4]).toBe(0);
    expect(midway[5]).toBeCloseTo(7.5 / 2.6, 6);
    expect(limbInfluence([chain], 0.25, 0.5, 1).slice(2)).toEqual([1, 0, 0, 0, 0, 0]);
    expect(limbInfluence([chain], 0.25, 0.249, 1).slice(2)).toEqual([0, 0, 0, 0, 0, 0]);
  });

  it('gives the physical front, rear and fringe identical weights regardless of depth or pigment UV', () => {
    const profile = volumeProfile('bip', 'female');
    const x = (0.3 - 0.5) * 2.6 * profile.scale,
      y = (0.79 - 0.5) * 2.6 * profile.scale;
    const mesh: VolumeMesh = {
      vertices: new Float32Array([
        x,
        y,
        0.2,
        0,
        0,
        1,
        0.3,
        0.79,
        x,
        y,
        -0.2,
        0,
        0,
        -1,
        0.5,
        0.5,
        x,
        y,
        0,
        0,
        0,
        2,
        0.3,
        0.79,
      ]),
      indices: new Uint16Array([0, 1, 2]),
    };
    const original = mesh.vertices.slice(),
      result = withLimbSkin(mesh, profile);
    expect(result.vertices).toBe(mesh.vertices);
    expect(result.vertices).toEqual(original);
    expect(result.skin!.vertices.slice(0, 8)).toEqual(result.skin!.vertices.slice(8, 16));
    expect(result.skin!.vertices.slice(0, 8)).toEqual(result.skin!.vertices.slice(16, 24));
    expect(result.skin!.vertices[2]).toBeGreaterThan(0.5);
  });

  it('bounds joint uniforms, clears unsupported and malformed channels, and never accumulates angle', () => {
    const skin = withLimbSkin(empty(), volumeProfile('bip', 'female')).skin!;
    const rest = restChannelValues(),
      values = { ...rest, armL: 999, armR: -999, wristL: NaN, footL: Infinity };
    const uniforms = skin.joints;
    updateLimbUniforms(skin, values);
    expect(uniforms[2]).toBeCloseTo((15 * Math.PI) / 180);
    expect(uniforms[6]).toBeCloseTo((-15 * Math.PI) / 180);
    expect(uniforms[10]).toBe(0);
    expect(uniforms[26]).toBe(0);
    for (let iteration = 0; iteration < 500; iteration++) updateLimbUniforms(skin, values);
    expect(skin.joints).toBe(uniforms);
    expect(uniforms[2]).toBeCloseTo((15 * Math.PI) / 180);
    updateLimbUniforms(skin);
    expect(LIMB_CHANNELS.every((_channel, index) => uniforms[index * 4 + 2] === 0)).toBe(true);
  });

  it('refines every affected fringe triangle while retaining a bounded source footprint', () => {
    for (const character of VOLUME_CHARACTERS)
      for (const variant of variants) {
        const profile = volumeProfile(character, variant);
        const mesh = withLimbSkin(withSoftFringe(empty(), profile), profile);
        expect(mesh.vertices.length / 8).toBeLessThan(2500);
        if (!mesh.skin) continue;
        for (let offset = 0; offset < mesh.indices.length; offset += 3) {
          const ids = [...mesh.indices.slice(offset, offset + 3)];
          if (
            !ids.some(
              index =>
                mesh.skin!.vertices[index * 8 + 2] > 0 || mesh.skin!.vertices[index * 8 + 3] > 0
            )
          )
            continue;
          const us = ids.map(index => mesh.vertices[index * 8 + 6]);
          const vs = ids.map(index => mesh.vertices[index * 8 + 7]);
          expect(Math.max(...us) - Math.min(...us)).toBeLessThanOrEqual(1 / 64);
          expect(Math.max(...vs) - Math.min(...vs)).toBeLessThanOrEqual(1 / 64);
        }
      }
  });
});

describe('GPU articulation owns one static influence buffer per lifetime', () => {
  it('uploads geometry once and only changes bounded joint uniforms between poses', () => {
    const gl = volumeGraphics(),
      profile = volumeProfile('bip', 'female');
    const mesh = withLimbSkin(withSoftFringe(empty(), profile), profile);
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh)!;
    gpu.upload(document.createElement('canvas'));
    const uploads = gl.bufferData.mock.calls.length;
    gpu.draw({ yaw: 0, pitch: 0 }, 0, 0, 1, { ...restChannelValues(), armL: 8 });
    expect(gl.uniform4fv).toHaveBeenLastCalledWith(expect.anything(), mesh.skin!.joints);
    expect(mesh.skin!.joints[2]).toBeCloseTo((8 * Math.PI) / 180);
    gpu.draw({ yaw: 0, pitch: 0 }, 0, 0, 1, { ...restChannelValues(), armL: -8 });
    expect(mesh.skin!.joints[2]).toBeCloseTo((-8 * Math.PI) / 180);
    expect(gl.bufferData).toHaveBeenCalledTimes(uploads);
    gpu.dispose();
    gpu.dispose();
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
  });

  it('retains the baked fallback and frees earlier objects when the skin allocation is rejected', () => {
    const gl = volumeGraphics(),
      profile = volumeProfile('bip', 'female');
    gl.createBuffer.mockReturnValueOnce({}).mockReturnValueOnce({}).mockReturnValueOnce(null);
    expect(
      createMeshGpu(document.createElement('canvas'), gl, withLimbSkin(empty(), profile))
    ).toBeNull();
    expect(gl.deleteBuffer.mock.calls).toEqual([
      [gl.createBuffer.mock.results[0].value],
      [gl.createBuffer.mock.results[1].value],
    ]);
    expect(gl.deleteTexture).toHaveBeenCalledOnce();
    expect(gl.deleteProgram).toHaveBeenCalledOnce();
    expect(gl.bufferData).not.toHaveBeenCalled();
  });
});

import { describe, expect, it } from 'vitest';
import { clothMesh, scarfKnotMesh } from '../cloth-geometry';
import { volumeProfile, VOLUME_SOURCE_EM, type VolumeProfile } from '../volume-geometry';
import { scarfFacetStyle, scarfWrapFacets, scarfKnotFacet, scarfKnotFacets } from '../scarf-wrap';

/** Read the emitted front-center section, not the collar's construction formula. */
function frontBand(profile: VolumeProfile) {
  const mesh = clothMesh(profile.collar);
  const rows: number[] = [];
  const widths: number[] = [];
  for (let i = 0; i < mesh.vertices.length; i += 8) {
    widths.push(Math.abs(mesh.vertices[i]));
    if (mesh.vertices[i + 2] > 0 && Math.abs(mesh.vertices[i]) < 1e-6)
      rows.push((mesh.vertices[i + 1] / (VOLUME_SOURCE_EM * profile.scale) + 0.5) * 192);
  }
  expect(rows.length).toBeGreaterThan(0);
  return { top: Math.min(...rows), bottom: Math.max(...rows), halfWidth: Math.max(...widths) };
}

function expectOscarNeck(profile: VolumeProfile) {
  const { top, bottom, halfWidth } = frontBand(profile);
  // Immutable source landmarks: the chin ends near row 109; the bow lies below
  // it, and the upper waistcoat ends near row 132. The cloth must fill that neck
  // interval without becoming the thin clavicle stripe rejected in review.
  expect(top).toBeGreaterThanOrEqual(109);
  expect(top).toBeLessThanOrEqual(112);
  expect(bottom).toBeGreaterThanOrEqual(129);
  expect(bottom).toBeLessThanOrEqual(132);
  expect(bottom - top).toBeGreaterThanOrEqual(18);
  expect(bottom - top).toBeLessThanOrEqual(22);
  expect(halfWidth).toBeGreaterThan(0.35);
}

function expectNimboFabric(profile: VolumeProfile) {
  const { top, bottom, halfWidth } = frontBand(profile);
  // Keep the accepted upper edge beneath the mouth, adding fabric downwards.
  // Source alpha >= 128 at x=96 ends at row 161 (female), 154 (male); allow
  // only two source pixels of cloth below that body base, not a hanging cape.
  const [upperMin, upperMax, bodyBase] =
    profile.variant === 'female' ? [135, 137, 161] : [131, 134, 154];
  expect(top).toBeGreaterThanOrEqual(upperMin);
  expect(top).toBeLessThanOrEqual(upperMax);
  expect(bottom - top).toBeGreaterThanOrEqual(20);
  expect(bottom - top).toBeLessThanOrEqual(24);
  expect(bottom).toBeLessThanOrEqual(bodyBase + 2);
  expect(halfWidth).toBeGreaterThan(1.15);
}

describe('a worn scarf continues around the actual body', () => {
  it.each(['bip', 'oscar', 'nimbo'] as const)(
    '%s has a closed front and rear ribbon',
    character => {
      for (const variant of ['female', 'male'] as const) {
        const profile = volumeProfile(character, variant);
        const mesh = clothMesh(profile.collar, profile);
        const depths: number[] = [];
        for (let i = 2; i < mesh.vertices.length; i += 8) depths.push(mesh.vertices[i]);
        expect(Math.min(...depths)).toBeLessThan(-0.2);
        expect(Math.max(...depths)).toBeGreaterThan(0.25);
        expect(mesh.vertices.length / 8).toBeLessThan(600);
      }
    }
  );
  it.each(['bip', 'oscar', 'nimbo'] as const)(
    '%s closes every seam and keeps the original knot separate',
    character => {
      for (const variant of ['female', 'male'] as const) {
        const collar = volumeProfile(character, variant).collar;
        const mesh = clothMesh(collar);
        for (let i = 0; i < mesh.vertices.length; i += 32) {
          const next = (i + 32) % mesh.vertices.length;
          for (let axis = 0; axis < 3; axis++)
            expect(mesh.vertices[i + 8 + axis]).toBeCloseTo(mesh.vertices[next + axis], 5);
          // Opposite swatch traversal meets the identical texel, including the
          // final/first circumference seam; geometry and normals never reverse.
          expect(mesh.vertices[i + 14]).toBe(mesh.vertices[next + 6]);
          expect(mesh.vertices[i + 15]).toBe(mesh.vertices[next + 7]);
        }
        const knot = scarfKnotMesh(collar);
        expect(knot.vertices).toHaveLength(64);
        expect(knot.indices).toHaveLength(12);
        const [attached, tail] = scarfKnotFacets(collar);
        const original = scarfKnotFacet(collar);
        expect(attached.origin).toEqual(original.origin);
        expect(attached.origin.y + attached.height).toBe(tail.origin.y);
        expect(attached.uv.bottom).toBe(tail.uv.top);
        expect(tail.origin.y + tail.height).toBeCloseTo(original.origin.y + original.height, 12);
        expect(tail.uv.bottom).toBe(original.uv.bottom);
        expect(tail.height).toBeGreaterThan(0);
        expect([...knot.vertices.slice(24, 32)]).toEqual([...knot.vertices.slice(32, 40)]);
        expect([...knot.vertices.slice(16, 24)]).toEqual([...knot.vertices.slice(40, 48)]);
      }
    }
  );

  // Hand-read landmarks from the immutable 192px source, deliberately independent
  // of the collar table: below the face, at the actual shell/shoulder/cloud level.
  it.each([['bip', 122 / 192, 141 / 192, 0.7]] as const)(
    '%s wraps its measured anatomical level',
    (character, top, bottom, halfWidth) => {
      for (const variant of ['female', 'male'] as const) {
        const profile = volumeProfile(character, variant);
        const mesh = clothMesh(profile.collar);
        const xs: number[] = [];
        for (let i = 0; i < mesh.vertices.length; i += 8) {
          const sourceY = mesh.vertices[i + 1] / (VOLUME_SOURCE_EM * profile.scale) + 0.5;
          if (mesh.vertices[i + 2] > 0 && Math.abs(mesh.vertices[i]) < 0.2) {
            expect(sourceY).toBeGreaterThan(top);
            expect(sourceY).toBeLessThan(bottom);
          }
          xs.push(Math.abs(mesh.vertices[i]));
        }
        expect(Math.max(...xs)).toBeGreaterThan(halfWidth);
      }
    }
  );

  it.each(['female', 'male'] as const)('Oscar %s fills the neck above the waistcoat', variant => {
    expectOscarNeck(volumeProfile('oscar', variant));
  });

  it.each(['female', 'male'] as const)(
    'Nimbo %s has substantial fabric below the same upper edge',
    variant => {
      expectNimboFabric(volumeProfile('nimbo', variant));
    }
  );

  it.each(['female', 'male'] as const)('rejects the previous thin scarf fits for %s', variant => {
    // Values retained from the pre-feedback source geometry captured in
    // scarf-flat-final-chromium: these local fixtures never mutate production.
    const oscar = volumeProfile('oscar', variant);
    oscar.collar = {
      ...oscar.collar,
      centerY: 0.37999,
      height: variant === 'female' ? 0.15 : 0.16,
      wrap: { ...oscar.collar.wrap!, frontDrop: variant === 'female' ? -0.01 : -0.03 },
    };
    expect(() => expectOscarNeck(oscar)).toThrow();
    const nimbo = volumeProfile('nimbo', variant);
    nimbo.collar = {
      ...nimbo.collar,
      centerY: variant === 'female' ? 0.419796 : 0.370396,
      height: variant === 'female' ? 0.18 : 0.19,
    };
    expect(() => expectNimboFabric(nimbo)).toThrow();
  });

  it('the CSS affine matrices reproduce every corner of the GPU facets', () => {
    const fit = volumeProfile('bip', 'female').collar;
    const facets = [...scarfWrapFacets(fit), ...scarfKnotFacets(fit)];
    const vertices = new Float32Array([...clothMesh(fit).vertices, ...scarfKnotMesh(fit).vertices]);
    for (const [index, facet] of facets.entries()) {
      const style = scarfFacetStyle(facet);
      const match = style['--scarf-facet-transform'].match(
        /translate3d\(([^)]+)\) matrix3d\(([^)]+)\)/
      )!;
      const origin = match[1].split(',').map(parseFloat);
      const matrix = match[2].split(',').map(Number);
      const width = parseFloat(style['--scarf-facet-width']),
        height = parseFloat(style['--scarf-facet-height']);
      for (const [corner, [u, v]] of [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ].entries()) {
        const i = index * 32 + corner * 8;
        for (let axis = 0; axis < 3; axis++) {
          const css = origin[axis] + matrix[axis] * width * u + matrix[4 + axis] * height * v;
          expect(css).toBeCloseTo(vertices[i + axis], 6);
        }
      }
      expect(style.backgroundPosition).not.toContain('NaN');
    }
  });
  it('the CSS texture mirror meets the same GPU texels on both sides of every seam', () => {
    for (const facet of scarfWrapFacets(volumeProfile('nimbo', 'male').collar)) {
      const style = scarfFacetStyle(facet);
      const width = parseFloat(style['--scarf-facet-width']);
      const imageWidth = (parseFloat(style.backgroundSize) / 100) * width;
      const left = (width - imageWidth) * (parseFloat(style.backgroundPosition) / 100);
      const uAt = (position: number) => {
        const x = style['--scarf-u-direction'] === -1 ? width - position : position;
        return (x - left) / imageWidth;
      };
      expect(uAt(0)).toBeCloseTo(facet.uv.left, 12);
      expect(uAt(width)).toBeCloseTo(facet.uv.right, 12);
    }
  });
});

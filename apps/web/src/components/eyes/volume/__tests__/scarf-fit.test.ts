import { describe, expect, it } from 'vitest';
import { clothMesh } from '../cloth-geometry';
import { volumeProfile } from '../volume-geometry';
const COLLAR = volumeProfile('monitor', 'male').collar;
import { mapScarfUv, scarfFrame, SCARF_ART } from '../scarf-fit';

describe('one fitted garment mapping', () => {
  it('changes neck width without changing fabric thickness or tail length', () => {
    const narrow = { ...COLLAR, radiusX: 0.2 };
    for (const v of [0, 89 / 192, 105.5 / 192, 122 / 192, 0.65, 145 / 192, 1]) {
      expect(mapScarfUv(narrow, 0.9, v).y).toBe(mapScarfUv(COLLAR, 0.9, v).y);
    }
    const upper = mapScarfUv(narrow, 0.5, 89 / 192);
    const lower = mapScarfUv(narrow, 0.5, 122 / 192);
    expect(lower.y - upper.y).toBeCloseTo(narrow.height, 12);
  });

  it('keeps both texture slices continuous and the mesh seam explicit', () => {
    const frame = scarfFrame(COLLAR);
    expect(frame.tailOffset + SCARF_ART.tailStart * frame.tailScale).toBeCloseTo(frame.split, 12);
    const mesh = clothMesh(COLLAR);
    const seam: number[] = [];
    for (let i = 0; i < mesh.vertices.length; i += 8) {
      if (Math.abs(mesh.vertices[i + 7] - SCARF_ART.tailStart) < 1e-6) seam.push(i);
    }
    expect(seam).toHaveLength(21);
    expect(new Set(seam.map(i => mesh.vertices[i + 1])).size).toBe(1);
  });
});

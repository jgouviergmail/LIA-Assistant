import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compilePoseSlots } from '../pose-slots';
import { roomModel } from '../art/room-models';
import { orientModel, rotateModelPoint, Model } from '../art/model';
import { floorVariant, propTextureKey } from '../art/prop-style';
it('bakes finite, non-degenerate authored geometry for each distinct functional furniture family', () => {
  const expected = [
    'chair',
    'bench',
    'display',
    'billiards',
    'sidetable',
    'tablelamp',
    'waterlily',
    'rock',
    'reeds',
    'shelf',
    'sink',
    'arcade',
    'poster',
    'drawingtable',
    'wallphone',
    'callbook',
    'archive',
    'readingdesk',
    'bar',
    'bottles',
    'jukebox',
    'labtable',
    'machine',
    'weightbench',
    'dumbbells',
    'mirror',
    'crystal',
    'toilet',
    'lounger',
    'vegetable',
    'nightstand',
    'alarm',
    'promiseboard',
    'sofa',
    'easel',
    'meetingtable',
  ];
  for (const kind of expected) {
    const props = WORLD.props.filter(p => p.kind === kind);
    expect(props.length, kind).toBeGreaterThan(0);
    for (const prop of props) {
      const mesh = roomModel(prop);
      expect(mesh, prop.id).not.toBeNull();
      expect(mesh!.length, prop.id).toBeGreaterThan(2);
      for (const part of mesh!) {
        expect(part.color).toMatch(/^#[0-9a-f]{6}$/i);
        if (part.kind === 'box') {
          for (const value of [part.width, part.depth, part.height])
            expect(value, prop.id).toBeGreaterThan(0);
          for (const value of [part.x, part.y, part.z])
            expect(Number.isFinite(value), prop.id).toBe(true);
          expect(part.x, prop.id).toBeGreaterThanOrEqual(-0.05);
          expect(part.y, prop.id).toBeGreaterThanOrEqual(-0.05);
          expect(part.x + part.width, prop.id).toBeLessThanOrEqual(prop.width + 0.05);
          expect(part.y + part.depth, prop.id).toBeLessThanOrEqual(prop.depth + 0.05);
          expect(part.z + part.height, prop.id).toBeLessThanOrEqual(
            Math.max(prop.height, 2.5) + 0.01
          );
        } else {
          expect(part.points.length).toBeGreaterThanOrEqual(3);
          for (const v of part.points) expect(Number.isFinite(v.x + v.y + v.z)).toBe(true);
        }
      }
    }
  }
  expect(roomModel(WORLD.props.find(p => p.kind === 'plant')!)).toBeNull();
});
it('rotates the furniture itself in world coordinates and round-trips every facing', () => {
  const model = new Model();
  model.box(0.1, 0.2, 0.4, 2.3, 0.6, 0.2, '#ff0000');
  model.panel(0.2, 0.5, 0.7, 1, 0.8, '#ffffff');
  let mesh = model.parts,
    w = 3,
    d = 1;
  for (let i = 0; i < 4; i++) {
    mesh = orientModel(mesh, w, d, 0);
    [w, d] = [d, w];
  }
  const rounded = (value: unknown) =>
    JSON.parse(
      JSON.stringify(value, (_, v: unknown) =>
        typeof v === 'number' ? Math.round(v * 1e9) / 1e9 : v
      )
    );
  expect(rounded(mesh)).toEqual(model.parts);
  expect(rotateModelPoint({ x: 0.2, y: 0.4, z: 1 }, 3, 1, 2)).toEqual({ x: 0.6, y: 0.2, z: 1 });
});
it('keeps checker parity across terrain chunks and distinct icons out of the shared texture identity', () => {
  for (const x of [0, 7, 8, 15, 16])
    for (const y of [0, 7, 8])
      expect(floorVariant('checker', x + 2, y)).not.toBe(floorVariant('checker', x, y));
  const easels = WORLD.props.filter(p => p.kind === 'easel');
  expect(new Set(easels.map(p => propTextureKey(p, false, false))).size).toBe(4);
  expect(new Set(easels.map(p => JSON.stringify(roomModel(p)))).size).toBe(4);
});

it('supports every seated avatar at the authoritative seat elevation in every chair orientation', () => {
  for (const slot of compilePoseSlots(WORLD)) {
    const prop = WORLD.props.find(item => item.id === slot.prop)!;
    if (prop.kind !== 'chair') continue;
    const x = slot.position.x - prop.x,
      y = slot.position.y - prop.y;
    const surfaces = roomModel(prop)!.filter(
      part =>
        part.kind === 'box' &&
        x >= part.x &&
        x <= part.x + part.width &&
        y >= part.y &&
        y <= part.y + part.depth
    );
    const top = Math.max(...surfaces.map(part => (part.kind === 'box' ? part.z + part.height : 0)));
    expect(top, prop.id).toBeCloseTo(slot.elevation, 6);
  }
});

it('leaves visible wall space between studio frames and adjacent window sills in projection', () => {
  const home = WORLD.zones.find(zone => zone.id === 'home')!;
  const frames = WORLD.props.filter(
    prop => prop.kind === 'poster' && prop.x >= home.x && prop.y >= home.y
  );
  expect(frames.length).toBeGreaterThan(0);
  for (const frame of frames) {
    const support = WORLD.props.find(prop => prop.id === frame.support)!;
    // Projection onto the supporting wall: an offset towards the viewer shifts
    // the apparent frame left, even when its ground footprint clears the bay.
    const vertices = roomModel(frame)!.flatMap(part =>
      part.kind === 'face'
        ? part.points
        : [
            { x: part.x, y: part.y, z: part.z },
            { x: part.x + part.width, y: part.y + part.depth, z: part.z + part.height },
          ]
    );
    const coordinates = vertices.map(v => frame.x + v.x - (frame.y + v.y - support.y - 0.625));
    const left = Math.min(...coordinates),
      right = Math.max(...coordinates);
    for (const window of WORLD.props.filter(
      prop => prop.kind === 'partition' && prop.wallWindow && prop.y === support.y
    )) {
      expect(
        right <= window.x + 0.07 - 0.09 || left >= window.x + 0.93 + 0.09,
        frame.id + ' / ' + window.id
      ).toBe(true);
    }
  }
});

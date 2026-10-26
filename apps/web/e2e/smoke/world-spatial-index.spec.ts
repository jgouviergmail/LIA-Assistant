import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';
import type { Point, Rect } from '../../src/features/world/types';

test('indexed masks preserve exact pixels and retain every sampled pickable silhouette', async ({
  page,
}, info) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const a = window.worldArtOracle,
      props = a.world.props,
      index = new a.WorldPropIndex(props);
    const maskCache = new Map<string, ReturnType<typeof a.paintProp>>();
    const mask = (p: (typeof props)[number]) => {
      let value = maskCache.get(p.id);
      if (!value) {
        value = a.paintProp(p, 1.5, false);
        maskCache.set(p.id, value);
      }
      return value;
    };
    const positions = a.world.zones.map(z => z.arrival);
    for (const kind of [
      'fountain',
      'tree',
      'meetingtable',
      'shelf',
      'bed',
      'sofa',
      'partition',
    ] as const) {
      const p = props.find(p => p.kind === kind);
      if (p)
        positions.push(
          { x: p.x + 0.4, y: p.y - 0.4 },
          { x: p.x + p.width + 0.2, y: p.y + p.depth + 0.2 }
        );
    }
    let pixelsDifferent = 0,
      frames = 0,
      pickSamples = 0,
      missingPicks = 0;
    const make = () => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 320;
      const c = canvas.getContext('2d', { willReadFrequently: true });
      if (!c) throw Error('No canvas');
      return { canvas, c };
    };
    const full = make(),
      fast = make();
    for (const point of positions)
      for (const facing of [0, 1, 2, 3] as const) {
        const at = a.createCamera({ width: 1, height: 1 }, point).center;
        const area = { x: at.x - 80, y: at.y - 112, width: 160, height: 160 };
        const unindexed = a.actorOccluders(props, point, area);
        const indexed = a.actorOccluders(index.query(area), point, area);
        const actor = a.paintActor(false, facing, 2, 1.5, 'teal', facing * 2, null, a.avatar);
        for (const [surface, occluders] of [
          [full, unindexed],
          [fast, indexed],
        ] as const) {
          const c = surface.c;
          c.setTransform(1, 0, 0, 1, 0, 0);
          c.globalCompositeOperation = 'source-over';
          c.clearRect(0, 0, 320, 320);
          c.setTransform(2, 0, 0, 2, -area.x * 2, -area.y * 2);
          c.drawImage(
            actor.canvas,
            at.x - actor.anchorX,
            at.y - actor.anchorY,
            actor.width,
            actor.height
          );
          c.globalCompositeOperation = 'destination-out';
          for (const prop of occluders) {
            const foot = a.createCamera({ width: 1, height: 1 }, prop).center,
              s = mask(prop);
            c.drawImage(s.canvas, foot.x - s.anchorX, foot.y - s.anchorY, s.width, s.height);
          }
        }
        const before = full.c.getImageData(0, 0, 320, 320).data,
          after = fast.c.getImageData(0, 0, 320, 320).data;
        for (let i = 0; i < before.length; i++) if (before[i] !== after[i]) pixelsDifferent++;
        frames++;
        actor.canvas.width = actor.canvas.height = 0;
      }
    for (const p of props.filter(p => p.height >= 0.1).filter((_p, i) => i % 7 === 0)) {
      const sprite = mask(p),
        pixels = sprite.canvas
          .getContext('2d')
          ?.getImageData(0, 0, sprite.canvas.width, sprite.canvas.height).data;
      if (!pixels) throw Error('No mask pixels');
      const at = a.createCamera({ width: 1, height: 1 }, p).center;
      for (let y = 0; y < sprite.canvas.height; y += 11)
        for (let x = 0; x < sprite.canvas.width; x += 11) {
          if (pixels[(y * sprite.canvas.width + x) * 4 + 3] <= 32) continue;
          const point = {
            x: at.x - sprite.anchorX + ((x + 0.5) * sprite.width) / sprite.canvas.width,
            y: at.y - sprite.anchorY + ((y + 0.5) * sprite.height) / sprite.canvas.height,
          };
          pickSamples++;
          if (!index.query({ ...point, width: 1, height: 1 }).includes(p)) missingPicks++;
        }
    }
    for (const sprite of maskCache.values()) sprite.canvas.width = sprite.canvas.height = 0;
    full.canvas.width = fast.canvas.width = 0;
    index.clear();
    return { frames, pixelsDifferent, pickSamples, missingPicks };
  });
  expect(result.frames).toBeGreaterThan(50);
  expect(result.pixelsDifferent).toBe(0);
  expect(result.pickSamples).toBeGreaterThan(500);
  expect(result.missingPicks).toBe(0);
  await info.attach('pixel-equivalence', {
    body: JSON.stringify(result),
    contentType: 'application/json',
  });
});
test('profile equivalent full-scan and indexed queries on the same campus', async ({
  page,
}, info) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const a = window.worldArtOracle,
      props = a.world.props,
      index = new a.WorldPropIndex(props);
    const points: { point: Point; area: Rect }[] = [];
    for (let y = 2; y < a.world.height; y += 5)
      for (let x = 2; x < a.world.width; x += 5) {
        const point = { x, y },
          at = a.createCamera({ width: 1, height: 1 }, point).center;
        points.push({ point, area: { x: at.x - 80, y: at.y - 112, width: 160, height: 160 } });
      }
    const run = (fast: boolean) => {
      let found = 0,
        candidates = 0;
      const started = performance.now();
      for (let turn = 0; turn < 16; turn++)
        for (const { point, area } of points) {
          const set = fast ? index.query(area) : props;
          candidates += set.length;
          found += a.actorOccluders(set, point, area).length;
        }
      return { ms: performance.now() - started, found, candidates };
    };
    run(false);
    run(true);
    const full = [],
      fast = [];
    for (let i = 0; i < 5; i++) {
      if (i % 2) {
        fast.push(run(true));
        full.push(run(false));
      } else {
        full.push(run(false));
        fast.push(run(true));
      }
    }
    index.clear();
    return { props: props.length, queries: points.length * 16, full, fast };
  });
  expect(result.fast.map(x => x.found)).toEqual(result.full.map(x => x.found));
  expect(result.fast[0].candidates).toBeLessThan(result.full[0].candidates / 10);
  console.info('index-profile', JSON.stringify(result));
  await info.attach('resource-profile', {
    body: JSON.stringify(result, null, 2),
    contentType: 'application/json',
  });
});

import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';

test('straight wall faces are opaque and uniform across their internal profile joints', async ({
  page,
}) => {
  await installArtOracle(page);
  const samples = await page.evaluate(() => {
    const { world, paintProp } = window.worldArtOracle;
    const wall = world.props.find(p => p.kind === 'partition')!;
    return [5, 10].map(wallConnections => {
      const prop = {
        ...wall,
        wallConnections,
        height: 2.8,
        wallFinish: 'slate' as const,
        wallWindow: false,
      };
      const sprite = paintProp(prop, 3, false),
        c = sprite.canvas.getContext('2d')!;
      return [0.15, 0.36, 0.38, 0.4, 0.6, 0.62, 0.64, 0.85].map(u => {
        const x = wallConnections === 5 ? u : 0.62,
          y = wallConnections === 5 ? 0.62 : u;
        return Array.from(
          c.getImageData(
            Math.round((sprite.anchorX + (x - y) * 32) * 3),
            Math.round((sprite.anchorY + (x + y) * 16 - 1.4 * 32) * 3),
            1,
            1
          ).data
        );
      });
    });
  });
  for (const side of samples)
    for (const pixel of side) {
      expect(pixel[3]).toBe(255);
      expect(pixel).toEqual(side[0]);
    }
});

test('foreground wall coping stays continuous beside the entire bottle shelf', async ({ page }) => {
  await installArtOracle(page);
  const samples = await page.evaluate(() => {
    const { world, paintProp, sortProps } = window.worldArtOracle;
    const shelf = world.props.find(p => p.kind === 'bottles')!;
    const walls = world.props.filter(
      p =>
        p.kind === 'partition' &&
        p.x >= shelf.x + shelf.width &&
        p.x < shelf.x + shelf.width + 1 &&
        p.y >= shelf.y &&
        p.y < shelf.y + shelf.depth
    );
    const canvas = document.createElement('canvas');
    canvas.width = 1000;
    canvas.height = 800;
    const c = canvas.getContext('2d')!;
    const project = (x: number, y: number, z = 0) => ({
      x: 500 + (x - shelf.x - y + shelf.y) * 64,
      y: 300 + (x - shelf.x + y - shelf.y) * 32 - z * 64,
    });
    const draw = (props: typeof world.props) => {
      c.clearRect(0, 0, canvas.width, canvas.height);
      for (const prop of props) {
        const sprite = paintProp(prop, 2, false),
          at = project(prop.x, prop.y);
        c.drawImage(sprite.canvas, at.x - sprite.anchorX * 2, at.y - sprite.anchorY * 2);
      }
      return walls.map(wall => {
        const at = project(wall.x + 0.5, wall.y + 0.5, wall.height + 0.005);
        return Array.from(c.getImageData(Math.round(at.x), Math.round(at.y), 1, 1).data);
      });
    };
    return { reference: draw(sortProps(walls)), furnished: draw(sortProps([...walls, shelf])) };
  });
  expect(samples.reference).toHaveLength(6);
  for (const pixel of samples.reference) expect(pixel[3]).toBe(255);
  expect(samples.furnished).toEqual(samples.reference);
});

test('bottle shelves stay open with bottles visible from both sides', async ({ page }) => {
  await installArtOracle(page);
  const counts = await page.evaluate(() => {
    const { world, paintProp } = window.worldArtOracle;
    const original = world.props.find(p => p.kind === 'bottles')!;
    return ([0, 1, 2, 3] as const).map(facing => {
      const swap =
        (original.facing === 0 || original.facing === 2) !== (facing === 0 || facing === 2);
      const sprite = paintProp(
        {
          ...original,
          facing,
          width: swap ? original.depth : original.width,
          depth: swap ? original.width : original.depth,
        },
        2,
        false
      );
      const pixels = sprite.canvas
        .getContext('2d')!
        .getImageData(0, 0, sprite.canvas.width, sprite.canvas.height).data;
      let bottles = 0;
      for (let i = 0; i < pixels.length; i += 4)
        if (
          pixels[i + 3] === 255 &&
          pixels[i + 1] > pixels[i] * 1.25 &&
          pixels[i + 1] > pixels[i + 2] * 1.1
        )
          bottles++;
      return bottles;
    });
  });
  for (const count of counts) expect(count).toBeGreaterThan(100);
});

test('fountain coping has four closed corners and a continuous level top', async ({ page }) => {
  await installArtOracle(page);
  const pixels = await page.evaluate(() => {
    const { world, paintProp } = window.worldArtOracle;
    const prop = world.props.find(p => p.kind === 'fountain')!;
    const sprite = paintProp(prop, 3, false),
      c = sprite.canvas.getContext('2d')!;
    const points = [
      [0.07, 0.07],
      [prop.width - 0.07, 0.07],
      [prop.width - 0.07, prop.depth - 0.07],
      [0.07, prop.depth - 0.07],
      [prop.width / 2, 0.07],
      [prop.width / 2, prop.depth - 0.07],
      [0.07, prop.depth / 2],
      [prop.width - 0.07, prop.depth / 2],
    ];
    return points.map(([x, y]) =>
      Array.from(
        c.getImageData(
          Math.round((sprite.anchorX + (x - y) * 32) * 3),
          Math.round((sprite.anchorY + (x + y) * 16 - 0.39 * 32) * 3),
          1,
          1
        ).data
      )
    );
  });
  for (const pixel of pixels) {
    expect(pixel[3]).toBe(255);
    expect(pixel.slice(0, 3).every(channel => channel > 210)).toBe(true);
    expect(pixel).toEqual(pixels[0]);
  }
});

test('rotated screen graphics stay on the front of the opaque housing', async ({ page }) => {
  await installArtOracle(page);
  const counts = await page.evaluate(() => {
    const { world, paintProp } = window.worldArtOracle;
    const original = world.props.find(p => p.kind === 'display')!;
    return ([0, 1, 2, 3] as const).map(facing => {
      const swap =
        (original.facing === 0 || original.facing === 2) !== (facing === 0 || facing === 2);
      const sprite = paintProp(
        {
          ...original,
          facing,
          width: swap ? original.depth : original.width,
          depth: swap ? original.width : original.depth,
        },
        2,
        false
      );
      const pixels = sprite.canvas
        .getContext('2d')!
        .getImageData(0, 0, sprite.canvas.width, sprite.canvas.height).data;
      let graphic = 0;
      for (let i = 0; i < pixels.length; i += 4)
        if (
          pixels[i] === 101 &&
          pixels[i + 1] === 215 &&
          pixels[i + 2] === 223 &&
          pixels[i + 3] === 255
        )
          graphic++;
      return graphic;
    });
  });
  expect(counts[0]).toBeGreaterThan(0);
  expect(counts[1]).toBeGreaterThan(0);
  expect(counts.slice(2)).toEqual([0, 0]);
});

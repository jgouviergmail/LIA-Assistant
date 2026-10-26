import { test, expect } from './fixtures';
import { installArtOracle } from '../fixtures/world-art';
test('speech artwork: the pointer joins the rounded card without an internal border', async ({
  page,
}, info) => {
  await installArtOracle(page);
  const colour = await page.evaluate(() => {
    const { SpeechPainter, speechBox, createSimulation, createCamera, world } =
      window.worldArtOracle;
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 360;
    document.body.append(canvas);
    const c = canvas.getContext('2d');
    if (!c) throw new Error('Canvas unavailable');
    c.fillStyle = '#131d30';
    c.fillRect(0, 0, 512, 360);
    const sim = createSimulation(world);
    sim.player.publicId = 'person';
    const camera = createCamera({ width: 512, height: 360 }, sim.player.position);
    camera.zoom = 1;
    new SpeechPainter().draw(c, camera, sim, [
      {
        id: 'one',
        speaker: 'person',
        label: 'Camille',
        text: 'Hello world',
        kind: 'private',
        created: 0,
        until: 5000,
      },
    ]);
    const box = speechBox({ x: 256, y: 81 }, 260, 61, camera, []);
    if (!box) throw new Error('Missing card');
    return Array.from(c.getImageData(256, Math.round(box.y + box.height), 1, 1).data);
  });
  expect(colour).toEqual([255, 252, 245, 255]);
  await page.screenshot({ path: info.outputPath('merged-speech-shape.png') });
});

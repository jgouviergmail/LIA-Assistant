import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';
test('authored functional objects and joinery: visual review sheet', async ({ page }, info) => {
  await installArtOracle(page);
  const count = await page.evaluate(() => {
    const { world, paintProp } = window.worldArtOracle;
    const kinds = [
      'telescope',
      'shelf',
      'wallphone',
      'easel',
      'alarm',
      'herbarium',
      'drawingtable',
      'meetingtable',
      'jukebox',
      'fountain',
      'bar',
      'partition',
    ];
    const sheet = document.createElement('canvas');
    sheet.id = 'objects';
    sheet.width = 1200;
    sheet.height = 960;
    const c = sheet.getContext('2d');
    if (!c) throw Error('Canvas unavailable');
    c.fillStyle = '#e7e5da';
    c.fillRect(0, 0, 1200, 960);
    kinds.forEach((kind, i) => {
      const prop = world.props.find(p => p.kind === kind);
      if (!prop) throw Error(kind);
      const sprite = paintProp(prop, 2);
      const x = (i % 4) * 300 + 150,
        y = Math.floor(i / 4) * 320 + 230;
      const scale = Math.min(1.5, 250 / sprite.width, 210 / sprite.height);
      const w = sprite.width * scale,
        h = sprite.height * scale;
      c.drawImage(sprite.canvas, x - w / 2, Math.floor(i / 4) * 320 + 25 + (210 - h) / 2, w, h);
      sprite.canvas.width = 0;
      c.fillStyle = '#23463f';
      c.font = '600 16px system-ui';
      c.textAlign = 'center';
      c.fillText(kind, x, y + 65);
    });
    document.body.appendChild(sheet);
    return kinds.length;
  });
  expect(count).toBe(12);
  await page.locator('#objects').screenshot({ path: info.outputPath('activity-objects.png') });
});

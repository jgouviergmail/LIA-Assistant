/** Navigate by authored place centres; a tiny minimap cannot target an object pixel exactly. */
import { expect, type Page } from '@playwright/test';
import { WORLD } from '../../src/features/world/definition';
import type { WorldProp } from '../../src/features/world/types';
export async function frameWorldProp(page: Page, prop: WorldProp, label: (id: string) => string) {
  const zone = WORLD.zones.find(
    z => prop.x >= z.x && prop.y >= z.y && prop.x < z.x + z.width && prop.y < z.y + z.height
  );
  if (!zone) throw new Error('Object has no authored place');
  const summary = page.locator('[data-world-place-menu]');
  const reveal = !(await summary.isVisible());
  const toggle = page.locator('.world-hud-toggle');
  if (reveal) await toggle.click();
  await summary.click();
  await page
    .locator('.world-map-directory')
    .getByRole('menuitem', { name: label(zone.id), exact: true })
    .click();
  await expect(summary).toBeFocused();
  const canvas = page.locator('canvas.world-canvas');
  const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error('Missing scene');
  const dx = prop.x + prop.width / 2 - (zone.x + zone.width / 2);
  const dy = prop.y + prop.depth / 2 - (zone.y + zone.height / 2);
  const zoom = Number((await page.locator('[data-world-zoom]').innerText()).replace('%', '')) / 100;
  const point = {
    x: bounds.x + bounds.width / 2 + (dx - dy) * 32 * zoom,
    y: bounds.y + bounds.height / 2 + ((dx + dy) * 16 - prop.height * 16) * zoom,
  };
  // Wide outdoor places do not fit one viewport. Pan through the real game
  // gesture instead of assuming that selecting a place exposes every object.
  for (let i = 0; i < 8; i++) {
    if (
      point.x > bounds.x + 80 &&
      point.x < bounds.x + bounds.width - 80 &&
      point.y > bounds.y + 150 &&
      point.y < bounds.y + bounds.height - 150
    ) {
      if (reveal) await toggle.click();
      return point;
    }
    const start = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
    const dx = Math.max(-bounds.width / 3, Math.min(bounds.width / 3, start.x - point.x));
    const dy = Math.max(-bounds.height / 3, Math.min(bounds.height / 3, start.y - point.y));
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + dx, start.y + dy, { steps: 8 });
    await page.mouse.up();
    point.x += dx;
    point.y += dy;
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  }
  throw new Error('Authored object could not be framed through the game camera');
}

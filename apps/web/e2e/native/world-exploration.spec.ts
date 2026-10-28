/** Native private route preference, compact widget group and direct scene seating. */
import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { player } from './world-arcade-helpers';
import { revealWorldControls, enterWorld } from '../fixtures/world-admission';
import { clickWorldProp } from '../fixtures/world-scene-navigation';
import { WORLD } from '../../src/features/world/definition';
import en from '../../locales/en/translation.json';

for (const width of [320, 390, 1280]) {
  test(`route, gestures and photo remain accessible widgets at ${width}px`, async ({
    browser,
    baseURL,
  }, info) => {
    if (!baseURL) throw new Error('Explicit isolated World URL required');
    const person = await player(browser, baseURL, 8, 'Exploration visitor', width);
    const { page, context } = person;
    try {
      await revealWorldControls(page);
      const group = page.locator('.world-device-controls');
      for (const name of [en.world.experience.route, en.world.emotes.title, en.world.photo.title]) {
        const button = group.getByRole('button', { name, exact: true });
        await expect(button).toBeVisible();
        const box = await button.boundingBox();
        if (!box) throw new Error('Missing widget geometry');
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
      }
      const route = group.getByRole('button', { name: en.world.experience.route, exact: true });
      const previous = await route.getAttribute('aria-pressed');
      await route.click();
      await expect(route).toHaveAttribute('aria-pressed', previous === 'true' ? 'false' : 'true');
      const desired = previous !== 'true';
      await expect
        .poll(
          async () =>
            (await (await context.request.get('/api/v1/world/experience')).json()).preferences
              .show_route
        )
        .toBe(desired);
      await expect(route).toBeFocused();
      expect(
        (
          await new AxeBuilder({ page })
            .include('.world-prototype')
            .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
            .analyze()
        ).violations
      ).toEqual([]);
      const seat = WORLD.props.find(prop => prop.key === 'atrium-n');
      if (!seat) throw new Error('Missing authored seat');
      await clickWorldProp(page, seat, id => en.world.zones[id as keyof typeof en.world.zones]);
      await expect.poll(() => person.view()?.you?.pose, { timeout: 30000 }).toMatch(/^atrium-n:/);
      await page.getByRole('button', { name: en.world.dashboard.stay, exact: true }).click();
      await page.screenshot({ path: info.outputPath('widgets-seated.png') });
      await page.reload();
      await enterWorld(page);
      await page.getByRole('button', { name: en.world.session.takeover, exact: true }).click();
      await expect.poll(() => person.view()?.controlling).toBe(true);
      await revealWorldControls(page);
      await expect(route).toHaveAttribute('aria-pressed', String(desired));
      expect(person.errors).toEqual([]);
      expect(person.paid).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
    } finally {
      await context.close();
    }
  });
}

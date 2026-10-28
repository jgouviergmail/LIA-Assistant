import { test, expect } from './fixtures';
import { player } from './world-arcade-helpers';
import { clickWorldProp } from '../fixtures/world-scene-navigation';
import { WORLD } from '../../src/features/world/definition';
import en from '../../locales/en/translation.json';

test('both workout benches acquire a real shared lying pose, animate and stand without an unavailable-seat refusal', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(180000);
  if (!baseURL) throw new Error('Explicit isolated World URL required');
  const person = await player(browser, baseURL, 8, 'Workout visitor', 1280);
  await person.page.emulateMedia({ reducedMotion: 'no-preference' });
  try {
    for (const key of ['workout-1', 'workout-2']) {
      const prop = WORLD.props.find(item => item.key === key);
      if (!prop) throw new Error('Missing workout bench');
      await clickWorldProp(
        person.page,
        prop,
        id => en.world.zones[id as keyof typeof en.world.zones]
      );
      await expect.poll(() => person.view()?.you?.pose, { timeout: 65000 }).toBe(key + ':0');
      expect(person.view()?.pose_result).toBe('accepted');
      await expect(person.page.locator('[data-world-cosmetic-effects]')).toHaveAttribute(
        'data-world-cosmetic-effects',
        /[1-8]/
      );
      const started = Date.now();
      const bounds = await person.page.locator('canvas.world-canvas').boundingBox();
      if (!bounds) throw new Error('Missing scene bounds');
      for (const at of [300, 1300, 2100]) {
        await expect.poll(() => Date.now() - started, { intervals: [50] }).toBeGreaterThan(at);
        await person.page.screenshot({
          path: info.outputPath(key + '-press-' + at + '.png'),
          clip: {
            x: bounds.x + bounds.width / 2 - 170,
            y: bounds.y + bounds.height / 2 - 145,
            width: 340,
            height: 260,
          },
        });
      }
      await expect.poll(() => person.view()?.you?.pose, { timeout: 10000 }).toBeNull();
      expect(person.view()?.pose_result).toBe('accepted');
    }
    expect(person.paid).toEqual([]);
    expect(person.errors).toEqual([]);
  } finally {
    await person.context.close();
  }
});

/** Real account preferences/admission; provider-free environment, native Canvas and DOM. */
import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { openNativeWorld, enterWorld, revealWorldControls } from '../fixtures/world-admission';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { installAudioProbe } from '../fixtures/world-sound';
import { objectApproaches } from '../../src/features/world/scene-interactions';
import { frameWorldProp, clickWorldProp } from '../fixtures/world-scene-navigation';
import { worldProofUrl } from './world-route';
import { signIn } from './world-arcade-helpers';
import { WORLD } from '../../src/features/world/definition';
import { AVATAR_PRESETS } from '../../src/features/world/avatar-presets';
import { parseWorldFrame, type WorldView } from '../../src/features/world/protocol';
import { cosmeticPropTarget } from '../../src/features/world/cosmetic-interactions';
import type { WorldProp } from '../../src/features/world/types';
import en from '../../locales/en/translation.json';

for (const width of [1280, 390]) {
  test(`editable presets, persisted seasons and visible decor respond at ${width}px`, async ({
    browser,
    baseURL,
  }, info) => {
    if (!baseURL) throw new Error('Disposable proof URL required');
    const context = await browser.newContext({
      viewport: { width, height: 844 },
      reducedMotion: 'no-preference',
      serviceWorkers: 'block',
    });
    try {
      await signIn(context, baseURL, 8);
      const page = await context.newPage();
      await installAudioProbe(page);
      const machineFiles = new Set<string>();
      page.on('request', request => {
        const path = new URL(request.url()).pathname;
        if (path.startsWith('/world/audio/v1/machine-'))
          machineFiles.add(path.split('/').at(-1) ?? '');
      });
      let view: WorldView | null = null;
      page.on('websocket', socket =>
        socket.on('framereceived', ({ payload }) => {
          const frame = parseWorldFrame(String(payload));
          if (frame.type === 'snapshot') view = frame;
        })
      );
      test.setTimeout(360000);
      await installOfflineFonts(page);
      let instant = Date.parse('2026-06-15T12:00:00Z');
      await page.route('**/api/v1/world/environment', route =>
        route.fulfill({
          json: {
            server_time: instant / 1000,
            timezone: 'UTC',
            weather: {
              temperature_c: 20,
              condition_code: 'Clear',
              wind_speed_kmh: 2,
              observed_at: new Date(instant - 1000).toISOString(),
              expires_at: new Date(instant + 3600000).toISOString(),
            },
          },
        })
      );
      let publications = 0;
      page.on('request', request => {
        if (request.method() === 'PUT' && request.url().endsWith('/world/avatar')) publications++;
      });
      await openNativeWorld(page, 'Decor visitor', worldProofUrl(baseURL, 'en'));
      const picker = page.getByRole('combobox', { name: en.world.avatar.presets.label });
      if (!(await picker.isVisible()))
        await page.getByRole('button', { name: en.world.avatar.change, exact: true }).click();
      for (const preset of AVATAR_PRESETS) {
        await picker.selectOption(preset.id);
        await expect(
          page.getByRole('combobox', { name: en.world.avatar.skin, exact: true })
        ).toHaveValue(preset.appearance.skin);
        if (preset.id === 'M03' || preset.id === 'F03')
          await page.screenshot({ path: info.outputPath('preset-' + preset.id + '.png') });
      }
      expect(publications).toBe(0);
      await page.screenshot({ path: info.outputPath('editable-presets.png') });
      await enterWorld(page);
      await expect(page.locator('.world-admission')).not.toBeVisible();
      expect(publications).toBe(1);
      await revealWorldControls(page);
      await page.getByRole('button', { name: en.world.help, exact: true }).click();
      for (const [label, value] of [
        [en.world.seasons.mode, 'winter'],
        [en.world.seasons.hemisphere, 'south'],
      ]) {
        const written = page.waitForResponse(
          response =>
            response.url().endsWith('/world/experience') && response.request().method() === 'PUT'
        );
        await page.getByRole('combobox', { name: label, exact: true }).selectOption(value);
        expect((await written).status()).toBe(200);
        await expect(page.getByRole('combobox', { name: label, exact: true })).toHaveValue(value);
      }
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations
      ).toEqual([]);
      await page.getByRole('button', { name: en.world.play, exact: true }).click();
      if (width === 1280) {
        await page.getByRole('button', { name: en.world.sound.settings, exact: true }).click();
        await page.getByRole('button', { name: en.world.sound.enable, exact: true }).click();
        await expect(
          page.getByRole('button', { name: en.world.sound.disable, exact: true })
        ).toHaveAttribute('aria-pressed', 'true');
        await page.keyboard.press('Escape');
      }
      const pond = WORLD.props.find(prop => prop.kind === 'pond');
      if (!pond) throw new Error('Missing authored pond');
      const label = (id: string) => en.world.zones[id as keyof typeof en.world.zones];
      async function exercise(prop: WorldProp, name: string) {
        const cuesBefore = await page.evaluate(
          () => window.worldSoundProbe.starts.filter(start => !start.loop).length
        );
        const previous = view?.you?.position;
        await clickWorldProp(page, prop, label);
        await expect(page.locator('[role="tooltip"]')).toHaveCount(0);
        // Selection is a walk intent; an effect cannot appear at the remote click.
        if (previous && Math.hypot(previous.x - prop.x, previous.y - prop.y) > 5)
          await expect(page.locator('[data-world-cosmetic-effects]')).toHaveAttribute(
            'data-world-cosmetic-effects',
            '0'
          );
        if (prop.kind !== 'weightbench')
          await expect
            .poll(
              () => {
                const at = view?.you?.position;
                return at
                  ? Math.min(
                      ...objectApproaches(prop, at).map(point =>
                        Math.hypot(point.x - at.x, point.y - at.y)
                      )
                    )
                  : Infinity;
              },
              { timeout: 65000 }
            )
            .toBeLessThan(0.65);
        await expect(page.locator('[data-world-cosmetic-effects]')).toHaveAttribute(
          'data-world-cosmetic-effects',
          /[1-8]/,
          { timeout: 65000 }
        );
        await expect(page.locator('.world-context-label')).not.toContainText('world.cosmetics.');
        if (prop.kind === 'weightbench')
          await expect.poll(() => view?.you?.pose).toMatch(/^workout-/);
        await page.screenshot({ path: info.outputPath('decor-' + name + '.png') });
        if (prop.kind === 'fountain' || prop.kind === 'weightbench' || prop.kind === 'pond') {
          const started = Date.now();
          await expect
            .poll(() => Date.now() - started, { intervals: [50] })
            .toBeGreaterThan(prop.kind === 'fountain' ? 700 : prop.kind === 'pond' ? 3200 : 1400);
          await page.screenshot({ path: info.outputPath('decor-' + name + '-active.png') });
        }
        await expect(page.locator('[data-world-cosmetic-effects]')).toHaveAttribute(
          'data-world-cosmetic-effects',
          '0',
          { timeout: 10000 }
        );
        if (prop.kind === 'weightbench') await expect.poll(() => view?.you?.pose).toBeNull();
        if (
          width === 1280 &&
          ['plant', 'billiards', 'fountain', 'machine', 'weightbench'].includes(prop.kind)
        ) {
          await expect
            .poll(() =>
              page.evaluate(() => window.worldSoundProbe.starts.filter(start => !start.loop).length)
            )
            .toBe(cuesBefore + (prop.kind === 'weightbench' ? 3 : 1));
          expect(await page.evaluate(() => window.worldSoundProbe.maximum)).toBeLessThanOrEqual(3);
        }
      }
      await exercise(pond, 'pond');
      if (width === 1280) {
        const fountain = WORLD.props.find(prop => prop.kind === 'fountain');
        if (!fountain) throw new Error('Missing fountain');
        await exercise(fountain, 'fountain');
        for (const kind of ['plant', 'billiards'] as const) {
          const prop = WORLD.props.find(item => item.kind === kind && cosmeticPropTarget(item));
          if (!prop) throw new Error('Missing ' + kind);
          await exercise(prop, kind);
        }
        for (const prop of WORLD.props.filter(item => item.kind === 'machine'))
          await exercise(prop, 'machine-' + prop.tone);
        expect([...machineFiles].sort()).toEqual([
          'machine-gantry.mp3',
          'machine-printer.mp3',
          'machine-start.mp3',
        ]);
        for (const prop of WORLD.props.filter(item => item.key?.startsWith('workout-')))
          await exercise(prop, prop.key ?? 'workout');
        const lamp = WORLD.props.find(item => item.kind === 'lamp' && cosmeticPropTarget(item));
        const screen = WORLD.props.find(
          item => item.kind === 'display' && cosmeticPropTarget(item)
        );
        if (!lamp || !screen) throw new Error('Missing stateful decor');
        async function arrived(prop: WorldProp) {
          await expect
            .poll(
              () => {
                const at = view?.you?.position;
                return at
                  ? Math.min(
                      ...objectApproaches(prop, at).map(point =>
                        Math.hypot(point.x - at.x, point.y - at.y)
                      )
                    )
                  : Infinity;
              },
              { timeout: 65000 }
            )
            .toBeLessThan(0.4);
          const since = Date.now();
          await expect.poll(() => Date.now() - since, { intervals: [50] }).toBeGreaterThan(350);
        }
        for (const state of ['on', 'off']) {
          await clickWorldProp(page, lamp, label);
          await arrived(lamp);
          await page.screenshot({ path: info.outputPath('lamp-' + state + '.png') });
        }
        for (let variant = 1; variant <= 5; variant++) {
          await clickWorldProp(page, screen, label);
          await arrived(screen);
          await expect(page.locator('.world-context-label')).not.toContainText('world.cosmetics.');
          await page.screenshot({ path: info.outputPath('screen-' + (variant % 5) + '.png') });
        }
      }
      const stored = await context.request.get('/api/v1/world/experience');
      expect(stored.status()).toBe(200);
      expect(await stored.json()).toMatchObject({
        preferences: { season_mode: 'winter', hemisphere: 'south' },
      });
      if (width === 1280) {
        instant = Date.parse('2026-12-15T00:00:00Z');
        await page.reload();
        await enterWorld(page);
        await page.getByRole('button', { name: en.world.session.takeover, exact: true }).click();
        await expect(
          page.getByRole('button', { name: en.world.session.takeover, exact: true })
        ).not.toBeVisible();
        await revealWorldControls(page);
        await expect(page.locator('.world-sky-badge')).toContainText(en.world.atmosphere.night);
        await frameWorldProp(page, pond, id => en.world.zones[id as keyof typeof en.world.zones]);
        await page.screenshot({ path: info.outputPath('winter-night.png') });
        for (const mode of ['spring', 'summer', 'autumn', 'off'] as const) {
          await revealWorldControls(page);
          await page.getByRole('button', { name: en.world.help, exact: true }).click();
          const written = page.waitForResponse(
            response =>
              response.url().endsWith('/world/experience') && response.request().method() === 'PUT'
          );
          await page
            .getByRole('combobox', { name: en.world.seasons.mode, exact: true })
            .selectOption(mode);
          expect((await written).status()).toBe(200);
          await expect(
            page.getByRole('combobox', { name: en.world.seasons.mode, exact: true })
          ).toHaveValue(mode);
          await page.getByRole('button', { name: en.world.play, exact: true }).click();
          await page.screenshot({ path: info.outputPath(mode + '-night.png') });
        }
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
    } finally {
      await context.close();
    }
  });
}

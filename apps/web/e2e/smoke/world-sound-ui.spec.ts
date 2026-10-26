import { test, expect } from '@playwright/test';
import { installApiCatchAll, registerRoutes } from '../fixtures/api-mock';
import { dashboardShellMocks } from '../fixtures/dashboard-shell';
import { makeTestUser } from '../fixtures/test-user';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { installAudioProbe } from '../fixtures/world-sound';
import { WORLD } from '../../src/features/world/definition';
import type { WorldMessage } from '../../src/features/world/message-protocol';

test.use({ hasTouch: true });
for (const width of [390, 1440])
  test(
    'world volume ' +
      width +
      ': stays opt-in and only a newly addressed private message rings once',
    async ({ page }, info) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await installAudioProbe(page);
      await installOfflineFonts(page);
      await installApiCatchAll(page);
      const user = makeTestUser();
      await registerRoutes(page, [
        ...dashboardShellMocks,
        { url: '**/api/v1/auth/me', json: user },
      ]);
      const garden = WORLD.zones.find(z => z.id === 'garden');
      if (!garden) throw new Error('No garden');
      await installInertWorldAdmission(page, user.id, { spawn: garden.arrival });
      let messages: WorldMessage[] = [];
      let reads = 0;
      await page.route('**/api/v1/world/messages/read', route => {
        reads++;
        return route.fulfill({
          json: { server_time: Date.now() / 1000, ttl_seconds: 1800, truncated: false, messages },
        });
      });
      const preferences: string[] = [];
      const requests: string[] = [];
      page.on('request', r => {
        if (r.url().includes('/world/audio/')) requests.push(r.url());
        if (r.method() !== 'GET' && /voice-preference|radio/.test(r.url()))
          preferences.push(r.url());
      });
      await page.goto('/fr/dashboard/world', { waitUntil: 'domcontentloaded' });
      await enterWorld(page);
      await expect(page.locator('canvas.world-canvas')).toBeVisible();
      await expect.poll(() => reads).toBeGreaterThan(0);
      expect(requests).toEqual([]);
      if (width === 390)
        await page.getByRole('button', { name: 'Commandes du monde', exact: true }).click();
      await page
        .getByRole('button', { name: 'Sons du monde', exact: true })
        [width === 390 ? 'tap' : 'click']();
      await expect(page.getByRole('dialog', { name: 'Sons du monde', exact: true })).toBeVisible();
      const slider = page.getByRole('slider', { name: 'Volume des sons du monde', exact: true });
      if (width === 390) {
        const track = await slider.evaluate(element => {
          const root = element.parentElement?.closest('[data-orientation="horizontal"]');
          if (!root) throw new Error('No slider track');
          const b = root.getBoundingClientRect();
          return { x: b.x, y: b.y, width: b.width, height: b.height };
        });
        const beforeScroll = await page.evaluate(() => window.scrollY);
        await page.touchscreen.tap(track.x + track.width * 0.55, track.y + track.height / 2);
        await expect(slider).not.toHaveAttribute('aria-valuenow', '100');
        expect(await page.evaluate(() => window.scrollY)).toBe(beforeScroll);
      }
      await slider.focus();
      await slider.press('Home');
      for (let i = 0; i < 37; i++) await slider.press('ArrowRight');
      await expect(slider).toHaveAttribute('aria-valuenow', '37');
      expect(requests).toEqual([]);

      await page.getByRole('button', { name: 'Activer les sons du monde', exact: true }).click();
      const supported = await page.evaluate(() => typeof AudioContext === 'function');
      if (!supported) {
        await expect(
          page.getByRole('button', { name: 'Activer les sons du monde', exact: true })
        ).toHaveAttribute('aria-pressed', 'false');
        await expect(
          page.getByRole('status').filter({ hasText: 'Le navigateur n’a pas pu activer le son.' })
        ).toBeVisible();
        expect(requests).toEqual([]);
        return;
      }
      await expect
        .poll(() => page.evaluate(() => window.worldSoundProbe.starts.some(s => s.loop)))
        .toBe(true);
      await expect(
        page.getByRole('button', { name: 'Couper les sons du monde', exact: true })
      ).toHaveAttribute('aria-pressed', 'true');
      await expect
        .poll(() => page.evaluate(() => window.worldSoundProbe.outputLevels()[0]))
        .toBeCloseTo(0.37, 2);
      await page.screenshot({ path: info.outputPath('mobile-world-volume.png') });

      const make = (id: string, outgoing = false): WorldMessage => ({
        id,
        sender_id: outgoing ? user.id : '81d739a2-dde9-4c36-8b01-28b181abb091',
        sender_alias: 'Peer',
        recipient_id: outgoing ? '81d739a2-dde9-4c36-8b01-28b181abb091' : user.id,
        recipient_alias: 'Explorer',
        outgoing,
        original: 'Bonjour',
        text: 'Bonjour',
        language: 'fr',
        status: 'original',
        created_at: Date.now() / 1000,
        expires_at: Date.now() / 1000 + 1800,
        receipt: null,
      });
      messages = [make('54ec38c4-bc86-470f-a40a-c3a0879ef010')];
      await expect
        .poll(
          () =>
            page.evaluate(
              () => window.worldSoundProbe.starts.filter(s => !s.loop && s.duration < 2).length
            ),
          { timeout: 10000 }
        )
        .toBe(1);
      messages.push(make('54ec38c4-bc86-470f-a40a-c3a0879ef011', true));
      const previous = reads;
      await expect.poll(() => reads, { timeout: 15000 }).toBeGreaterThan(previous + 1);
      expect(
        await page.evaluate(
          () => window.worldSoundProbe.starts.filter(s => !s.loop && s.duration < 2).length
        )
      ).toBe(1);
      await page.getByRole('button', { name: 'Couper les sons du monde', exact: true }).click();
      await expect
        .poll(() => page.evaluate(() => window.worldSoundProbe.context?.state))
        .toBe('suspended');
      messages.push(make('54ec38c4-bc86-470f-a40a-c3a0879ef012'));
      const muted = reads;
      await expect.poll(() => reads, { timeout: 10000 }).toBeGreaterThan(muted);
      expect(
        await page.evaluate(
          () => window.worldSoundProbe.starts.filter(s => !s.loop && s.duration < 2).length
        )
      ).toBe(1);
      await slider.press('Escape');
      await expect(page.getByRole('button', { name: 'Sons du monde', exact: true })).toBeFocused();
      await page.getByRole('button', { name: 'Sons du monde', exact: true }).click();
      await expect(slider).toHaveAttribute('aria-valuenow', '37');
      expect(preferences).toEqual([]);
      await page.screenshot({ path: info.outputPath('mobile-sound-widget.png') });
    }
  );

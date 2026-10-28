/** Real game authority, native admission and independent browser processes. */
import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { CABINET_GAMES, type CabinetId } from '../../src/features/world/game-catalogue';
import en from '../../locales/en/translation.json';
import {
  player,
  openCabinet,
  choice,
  finish,
  resumeAfterReload,
  type Player,
} from './world-arcade-helpers';

for (const cabinet of Object.keys(CABINET_GAMES) as CabinetId[])
  test(`native humans and computer finish ${cabinet}`, async ({ browser, baseURL }, info) => {
    test.setTimeout(360000);
    if (!baseURL) throw new Error('Disposable proof URL required');
    const peer = await browser.browserType().launch({ headless: true });
    const third = await browser.browserType().launch({ headless: true });
    const people: Player[] = [];
    try {
      const host = await player(browser, baseURL, 8, 'Alex', 1280);
      people.push(host);
      const guest = await player(peer, baseURL, 7, 'Sam', 320);
      people.push(guest);
      const observer = await player(third, baseURL, 6, 'Robin', 390);
      people.push(observer);
      await openCabinet(host, cabinet);
      expect(host.sent).toEqual([]);
      await choice(host, en.world.arcade.wait);
      await expect.poll(() => host.view()?.game?.phase).toBe('waiting');
      await openCabinet(guest, cabinet);
      expect(guest.view()?.game).toBeNull();
      await choice(guest, en.world.arcade.join);
      await expect(host.page.getByText(en.world.arcade.fresh_board)).toBeVisible();
      await choice(host, en.world.arcade.accept.replace('{{player}}', 'Sam'));
      await expect.poll(() => guest.view()?.game?.phase).toBe('playing_human');
      await openCabinet(observer, cabinet);
      await expect(observer.page.getByText(en.world.arcade.occupied)).toBeVisible();
      expect(observer.view()?.game).toBeNull();
      await observer.page.keyboard.press('Escape');
      for (const person of [host, guest])
        expect(
          (
            await new AxeBuilder({ page: person.page })
              .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
              .analyze()
          ).violations
        ).toEqual([]);
      await guest.page.screenshot({ path: info.outputPath('mobile-human-board.png') });
      if (cabinet === 'arcade-tic-tac-toe') {
        const cells = host.page.getByRole('gridcell');
        await cells.nth(0).focus();
        await cells.nth(0).press('ArrowRight');
        await expect(cells.nth(1)).toBeFocused();
        await cells.nth(1).press('Home');
        await expect(cells.nth(0)).toBeFocused();
      }
      await finish([host, guest]);
      await expect.poll(() => guest.view()?.game?.phase).toBe('finished');
      const round = host.view()?.game?.round_id;
      const hostNumber = host.view()?.game?.your_number;
      if (!round || !hostNumber) throw new Error('No finished authoritative round');
      await choice(host, en.world.arcade.rematch);
      // One readiness is recorded and announced, and alone it starts nothing.
      await expect.poll(() => host.view()?.game?.rematch_ready ?? []).toContain(hostNumber);
      expect(host.view()?.game?.round_id).toBe(round);
      await choice(guest, en.world.arcade.rematch);
      await expect.poll(() => host.view()?.game?.round_id).not.toBe(round);
      await expect.poll(() => guest.view()?.game?.round_id).toBe(host.view()?.game?.round_id);
      if (cabinet === 'arcade-tic-tac-toe') await resumeAfterReload(guest, cabinet);
      await choice(guest, en.world.arcade.leave, () => openCabinet(guest, cabinet));
      await expect.poll(() => guest.view()?.game).toBeNull();
      await choice(host, en.world.arcade.leave, () => openCabinet(host, cabinet));
      await expect.poll(() => host.view()?.game).toBeNull();
      await openCabinet(host, cabinet);
      await choice(host, en.world.arcade.computer);
      await expect.poll(() => host.view()?.game?.phase).toBe('playing_computer');
      await finish([host]);
      await expect.poll(() => host.view()?.game?.phase).toBe('finished');
      await host.page.screenshot({ path: info.outputPath('computer-result.png') });
      await choice(host, en.world.arcade.leave, () => openCabinet(host, cabinet));
      for (const person of people) {
        expect(person.errors).toEqual([]);
        expect(person.paid).toEqual([]);
      }
    } finally {
      await info.attach('native-game-evidence', {
        body: JSON.stringify(
          people.map(person => ({
            view: person.view(),
            sent: person.sent,
            errors: person.errors,
            paid: person.paid,
            bytes: person.bytes,
            confirmationsMs: person.confirmationsMs,
            results: person.results,
          }))
        ),
        contentType: 'application/json',
      });
      await Promise.all(people.map(person => person.context.close()));
      await peer.close();
      await third.close();
    }
  });

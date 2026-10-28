/** Five independent native clients: two human tables and one computer table. */
import { test, expect, type Browser } from './fixtures';
import { player, openCabinet, choice, finish, type Player } from './world-arcade-helpers';
import en from '../../locales/en/translation.json';

test('three cabinets remain independent with five real browser processes', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(360000);
  if (!baseURL) throw new Error('Disposable proof URL required');
  const engines: Browser[] = [browser];
  const people: Player[] = [];
  try {
    for (let index = 0; index < 5; index++) {
      const engine = index === 0 ? browser : await browser.browserType().launch({ headless: true });
      if (index !== 0) engines.push(engine);
      people.push(
        await player(engine, baseURL, 8 - index, `Player ${index}`, index % 2 ? 390 : 1280)
      );
    }
    for (const [hostIndex, guestIndex, cabinet] of [
      [0, 1, 'arcade-tic-tac-toe'],
      [2, 3, 'arcade-four-in-row'],
    ] as const) {
      const host = people[hostIndex],
        guest = people[guestIndex];
      await openCabinet(host, cabinet);
      await choice(host, en.world.arcade.wait);
      await expect.poll(() => host.view()?.game?.phase).toBe('waiting');
      await openCabinet(guest, cabinet);
      await choice(guest, en.world.arcade.join);
      await choice(host, en.world.arcade.accept.replace('{{player}}', `Player ${guestIndex}`));
      await expect.poll(() => guest.view()?.game?.phase).toBe('playing_human');
    }
    await openCabinet(people[4], 'arcade-reversi');
    await choice(people[4], en.world.arcade.computer);
    await expect.poll(() => people[4].view()?.game?.phase).toBe('playing_computer');
    await expect(people[4].page.getByRole('grid')).toBeVisible();
    await people[4].page
      .getByRole('grid')
      .screenshot({ path: info.outputPath('three-cabinets-reversi-board.png') });
    await people[3].page
      .getByRole('table')
      .screenshot({ path: info.outputPath('three-cabinets-mobile-four-board.png') });
    const rounds = people.map(person => person.view()?.game?.round_id);
    expect(new Set(rounds).size).toBe(3);
    for (const person of people) {
      expect(person.view()?.cabinets).toHaveLength(3);
      expect(person.view()?.game_request).toBeNull();
    }
    await info.attach('five-client-active', {
      body: JSON.stringify(people.map(person => person.view())),
      contentType: 'application/json',
    });
    await Promise.all([
      finish(people.slice(0, 2)),
      finish(people.slice(2, 4)),
      finish([people[4]]),
    ]);
    for (const person of people) {
      await expect.poll(() => person.view()?.game?.phase).toBe('finished');
      expect(person.errors).toEqual([]);
      expect(person.paid).toEqual([]);
    }
  } finally {
    await info.attach('five-client-results', {
      body: JSON.stringify(
        people.map(person => ({
          game: person.view()?.game,
          commands: person.sent,
          results: person.results,
          bytes: person.bytes,
          confirmationsMs: person.confirmationsMs,
        }))
      ),
      contentType: 'application/json',
    });
    await Promise.all(people.map(person => person.context.close()));
    await Promise.all(engines.slice(1).map(engine => engine.close()));
  }
});

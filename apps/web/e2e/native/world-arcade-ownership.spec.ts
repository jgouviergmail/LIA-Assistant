/** A second tab cannot inherit game consent; Escape withdraws exactly once. */
import { test, expect } from './fixtures';
import { player, observePlayer, openCabinet, choice } from './world-arcade-helpers';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { openNativeWorld, enterWorld } from '../fixtures/world-admission';
import { worldProofUrl } from './world-route';
import en from '../../locales/en/translation.json';

test('same-account tab takeover withdraws the old private board and Escape leaves once', async ({
  browser,
  baseURL,
}, info) => {
  if (!baseURL) throw new Error('Disposable proof URL required');
  const host = await player(browser, baseURL, 8, 'Alex', 1280);
  const cabinet = 'arcade-tic-tac-toe';
  try {
    await openCabinet(host, cabinet);
    await choice(host, en.world.arcade.computer);
    await expect.poll(() => host.view()?.game?.phase).toBe('playing_computer');
    const round = host.view()?.game?.round_id;
    const tab = await host.context.newPage();
    // The same account in a second tab: its own socket, commands and verdicts.
    const successor = observePlayer(tab, host.context);
    const sent = successor.sent;
    await installOfflineFonts(tab);
    await openNativeWorld(tab, 'Alex', worldProofUrl(baseURL, 'en'));
    await enterWorld(tab);
    await tab.getByRole('button', { name: en.world.session.takeover, exact: true }).click();
    await expect.poll(() => host.view()?.controlling).toBe(false);
    await expect(host.page.getByRole('grid')).toHaveCount(0);
    expect(host.view()?.game).toBeNull();
    await openCabinet(successor, cabinet);
    await expect(
      tab.getByRole('button', { name: en.world.arcade.resume, exact: true })
    ).toBeVisible();
    expect(successor.view()?.game?.round_id).toBe(round);
    await expect(tab.getByRole('grid')).toHaveCount(0);
    expect(sent).toEqual([]);
    await choice(successor, en.world.arcade.resume);
    await expect.poll(() => successor.view()?.game?.needs_rejoin).toBe(false);
    await expect(tab.getByRole('grid')).toBeVisible();
    await tab.keyboard.press('Escape');
    await expect(tab.getByRole('dialog')).toHaveCount(0);
    await expect.poll(() => successor.view()?.game).toBeNull();
    expect(
      sent.map(value => {
        const frame: unknown = JSON.parse(value);
        return frame && typeof frame === 'object' && 'action' in frame ? frame.action : null;
      })
    ).toEqual(['rejoin', 'leave']);
    await info.attach('returned-focus', {
      body: JSON.stringify({
        active: await tab.evaluate(() => ({
          tag: document.activeElement?.tagName,
          name: document.activeElement?.getAttribute('aria-label'),
          text: document.activeElement?.textContent?.slice(0, 80),
        })),
      }),
      contentType: 'application/json',
    });
    // In-scene activation returns focus to the connected canvas.
    await expect
      .poll(
        async () =>
          await tab.locator('canvas.world-canvas').evaluate(node => node === document.activeElement)
      )
      .toBe(true);
    await info.attach('same-account-ownership', {
      body: JSON.stringify({ old: host.view(), current: successor.view(), sent }),
      contentType: 'application/json',
    });
  } finally {
    await host.context.close();
  }
});

import { expect, type Browser, type BrowserContext, type Page } from './fixtures';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { openNativeWorld, enterWorld } from '../fixtures/world-admission';
import { worldProofUrl } from './world-route';
import { parseWorldFrame, type WorldView } from '../../src/features/world/protocol';
import type { GameMove, GameOutcome, GameView } from '../../src/features/world/game-protocol';
import {
  CABINET_GAMES,
  compileGameCabinets,
  type CabinetId,
} from '../../src/features/world/game-catalogue';
import { WORLD } from '../../src/features/world/definition';
import en from '../../locales/en/translation.json';
import { clickWorldProp } from '../fixtures/world-scene-navigation';

export interface Player {
  page: Page;
  context: BrowserContext;
  view(): WorldView | null;
  sent: string[];
  errors: string[];
  paid: string[];
  bytes: number[];
  confirmationsMs: number[];
  results: GameView[];
  /** The authority's verdict on the last game command this page sent, once received. */
  lastVerdict(): GameOutcome['result'] | undefined;
}
/** Bounded retry after the authority's own `rate_limited` backpressure. */
const RATE_LIMIT_ATTEMPTS = 6;
const RATE_LIMIT_BACKOFF_MS = 200;

/** Bind a context to one inert proof account: the host sets its real session cookie. */
export async function signIn(context: BrowserContext, baseURL: string, index: number) {
  expect(
    (
      await context.request.post('/api/v1/world-proof/session', {
        headers: { Origin: new URL(baseURL).origin },
        data: { index },
      })
    ).status()
  ).toBe(200);
}

export async function player(
  browser: Browser,
  baseURL: string,
  index: number,
  alias: string,
  width: number
): Promise<Player> {
  const context = await browser.newContext({
    baseURL,
    viewport: { width, height: 844 },
    serviceWorkers: 'block',
    reducedMotion: 'reduce',
  });
  await signIn(context, baseURL, index);
  const page = await context.newPage();
  const person = observePlayer(page, context);
  await installOfflineFonts(page);
  await openNativeWorld(page, alias, worldProofUrl(baseURL, 'en'));
  await enterWorld(page);
  await expect.poll(() => person.view()?.controlling).toBe(true);
  return person;
}

/**
 * Everything a journey reads from one page's World socket and requests, from
 * its next socket on: snapshots, game commands and their verdicts, page errors
 * and any paid read. Attach it before the page opens the World.
 */
export function observePlayer(page: Page, context: BrowserContext): Player {
  let current: WorldView | null = null;
  const sent: string[] = [],
    errors: string[] = [],
    paid: string[] = [];
  const bytes: number[] = [],
    confirmationsMs: number[] = [];
  const results: GameView[] = [];
  const awaiting = new Map<number, number>();
  // A sequence names a command within ONE socket generation: a reload restarts it.
  const verdicts = new Map<string, GameOutcome['result']>();
  let generations = 0;
  let last: string | null = null;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/briefing\/synthesis|agents\/chat/.test(request.url())) paid.push(request.url());
  });
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    const generation = ++generations;
    socket.on('framereceived', ({ payload }) => {
      const frame = parseWorldFrame(String(payload));
      if (frame.type === 'snapshot') {
        current = frame;
        if (
          frame.game?.phase === 'finished' &&
          !results.some(game => game.round_id === frame.game?.round_id) &&
          results.length < 8
        )
          results.push(frame.game);
        if (bytes.length < 2000) bytes.push(Buffer.byteLength(String(payload)));
        for (const receipt of frame.receipts) {
          if (receipt.kind !== 'game') continue;
          verdicts.set(`${generation}:${receipt.seq}`, receipt.outcome.result);
          const started = awaiting.get(receipt.seq);
          if (started === undefined) continue;
          confirmationsMs.push(Date.now() - started);
          awaiting.delete(receipt.seq);
        }
      }
    });
    socket.on('framesent', ({ payload }) => {
      const frame: unknown = JSON.parse(String(payload));
      if (frame && typeof frame === 'object' && 'type' in frame && frame.type === 'game') {
        sent.push(String(payload));
        if ('seq' in frame && typeof frame.seq === 'number') {
          awaiting.set(frame.seq, Date.now());
          last = `${generation}:${frame.seq}`;
        }
      }
    });
  });
  return {
    page,
    context,
    view: () => current,
    sent,
    errors,
    paid,
    bytes,
    confirmationsMs,
    results,
    lastVerdict: () => (last === null ? undefined : verdicts.get(last)),
  };
}
export async function openCabinet(person: Player, cabinet: CabinetId) {
  const prop = compileGameCabinets(WORLD).find(item => item.id === cabinet)?.prop;
  if (!prop) throw new Error('Missing authored cabinet');
  const object = WORLD.props.find(item => item.id === prop);
  if (!object) throw new Error('Missing cabinet geometry');
  await clickWorldProp(
    person.page,
    object,
    id => en.world.zones[id as keyof typeof en.world.zones]
  );
  await expect(
    person.page.getByRole('dialog', {
      name: en.world.arcade.games[CABINET_GAMES[cabinet]].title,
      exact: true,
    })
  ).toBeVisible({ timeout: 30000 });
}
/**
 * One deliberate game action, sent as a person would and judged by its receipt.
 * The account's input budget is the authority's (`world_arcade_input_rate`,
 * never copied here): its `rate_limited` verdict is backpressure, so the same
 * action is chosen again after a growing pause. Any other verdict stands.
 */
async function deliberate(person: Player, act: (attempt: number) => Promise<void>) {
  for (let attempt = 0; attempt < RATE_LIMIT_ATTEMPTS; attempt++) {
    const before = person.sent.length;
    await act(attempt);
    await expect.poll(() => person.sent.length).toBeGreaterThan(before);
    await expect.poll(() => person.lastVerdict()).not.toBeUndefined();
    if (person.lastVerdict() !== 'rate_limited') return;
    await new Promise(resolve => setTimeout(resolve, RATE_LIMIT_BACKOFF_MS * (attempt + 1)));
  }
  throw new Error('The authority refused a deliberate action as rate limited on every attempt');
}
/** `reopen` restores a control whose own press closed its surface (Leave). */
export async function choice(person: Player, label: string, reopen?: () => Promise<void>) {
  const control = person.page.getByRole('button', { name: label, exact: true });
  await deliberate(person, async attempt => {
    if (attempt > 0 && reopen && !(await control.isVisible())) await reopen();
    await expect(control).not.toHaveAttribute('aria-disabled', 'true');
    await control.click();
  });
}
export async function move(person: Player, value: GameMove) {
  const prior = person.view()?.game?.revision;
  const target =
    value.game === 'four_in_row'
      ? person.page.locator(`[data-world-game-column="${value.column}"]`)
      : value.cell === null
        ? person.page.getByRole('button', { name: en.world.arcade.pass, exact: true })
        : person.page.locator(`[data-world-game-cell="${value.cell}"]`);
  await deliberate(person, async () => {
    await expect(target).not.toHaveAttribute('aria-disabled', 'true');
    if ((person.page.viewportSize()?.width ?? 0) > 767) await target.press('Enter');
    else await target.click();
  });
  await expect.poll(() => person.view()?.game?.revision).not.toBe(prior);
}
export async function finish(people: Player[]) {
  for (let count = 0; count < 130; count++) {
    const result = people[0].view()?.game;
    if (result?.phase === 'finished') {
      expect(['win', 'draw']).toContain(result.reason);
      expect(result.position.result).not.toBe('playing');
      expect(result.winner).toBe(
        result.position.result === 'draw' ? null : result.position.result === 'one' ? 1 : 2
      );
      return;
    }
    const actor = people.find(person => {
      const game = person.view()?.game;
      return game && game.position.turn === game.your_number && game.legal_moves.length > 0;
    });
    if (!actor) {
      await expect
        .poll(
          () =>
            people.some(person => (person.view()?.game?.legal_moves.length ?? 0) > 0) ||
            people[0].view()?.game?.phase === 'finished'
        )
        .toBe(true);
      continue;
    }
    const value = actor.view()?.game?.legal_moves[0];
    if (!value) throw new Error('No legal authoritative move');
    await move(actor, value);
  }
  throw new Error('Game exceeded its finite rules bound');
}
export async function resumeAfterReload(person: Player, cabinet: CabinetId) {
  const round = person.view()?.game?.round_id;
  await person.page.reload();
  await enterWorld(person.page);
  await person.page.getByRole('button', { name: en.world.session.takeover, exact: true }).click();
  await expect.poll(() => person.view()?.controlling).toBe(true);
  await openCabinet(person, cabinet);
  await expect(
    person.page.getByRole('button', { name: en.world.arcade.resume, exact: true })
  ).toBeVisible();
  await expect(person.page.getByRole('grid')).toHaveCount(0);
  expect(person.view()?.game?.round_id).toBe(round);
  await choice(person, en.world.arcade.resume);
  await expect.poll(() => person.view()?.game?.needs_rejoin).toBe(false);
  await expect.poll(() => person.view()?.game?.paused).toBe(false);
}

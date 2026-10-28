/**
 * Hermetic arcade journey: the cabinet opens through the scene's own pixel
 * picking, a tiny authoritative desk answers every game command over the
 * World socket, and the board only ever draws what a snapshot carried.
 * Native SQL/Redis authority, real rules and two-player rounds stay in
 * `native/world-arcade*.spec.ts`.
 */
import { test, expect } from '../fixtures';
import type { Locator, Page } from '@playwright/test';
import {
  installInertWorldAdmission,
  type InertWorld,
  type WorldCommandAuthority,
  type WorldCommandOutcome,
} from '../fixtures/world-session';
import { appConfig } from '../fixtures/dashboard-shell';
import { enterWorld } from '../fixtures/world-admission';
import { clickWorldProp } from '../fixtures/world-scene-navigation';
import { scanPage } from '../a11y/scan';
import { WORLD } from '../../src/features/world/definition';
import {
  CABINET_GAMES,
  compileGameCabinets,
  type CabinetId,
} from '../../src/features/world/game-catalogue';
import type { CabinetView, GameOutcome, GameView } from '../../src/features/world/game-protocol';
import { FRESH_SNAPSHOT_MS } from '../../src/features/world/movement';
import en from '../../locales/en/translation.json';

const CABINET: CabinetId = 'arcade-tic-tac-toe';
const TITLE = en.world.arcade.games.tic_tac_toe.title;
const PANEL = '[data-world-native-panel]';
const LINES = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

function roundId(index: number): string {
  return `6a7c0000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`;
}
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/**
 * The server side of one cabinet, reduced to what the journey needs: its
 * computer always takes the first free cell, so every round is finite and the
 * same. It checks round and revision like the real rules, so a client bug
 * reads as a refusal instead of a silently accepted move.
 */
function ticTacToeDesk(ownerId: string) {
  let board = Array<number>(9).fill(0);
  let round: string | null = null;
  let revision = 0;
  let rounds = 0;
  let held: Promise<void> | null = null;
  let refusal: GameOutcome['result'] | null = null;
  const actions: string[] = [];
  const result = (): GameView['position']['result'] => {
    const line = LINES.find(
      ([a, b, c]) => board[a] !== 0 && board[a] === board[b] && board[a] === board[c]
    );
    if (line) return board[line[0]] === 1 ? 'one' : 'two';
    return board.every(cell => cell !== 0) ? 'draw' : 'playing';
  };
  const game = (): GameView | null => {
    if (round === null) return null;
    const outcome = result();
    const now = Date.now() / 1000;
    return {
      cabinet: CABINET,
      round_id: round,
      revision,
      phase: outcome === 'playing' ? 'playing_computer' : 'finished',
      computer: true,
      position: { game: 'tic_tac_toe', board: [...board], turn: 1, result: outcome },
      players: [{ id: ownerId, alias: 'Explorer', number: 1 }],
      your_number: 1,
      needs_rejoin: false,
      paused: false,
      turn_until: now + 60,
      expires_at: now + 900,
      reconnect_until: null,
      pending: null,
      legal_moves:
        outcome === 'playing'
          ? board.flatMap((cell, index) =>
              cell === 0 ? [{ game: 'tic_tac_toe' as const, cell: index }] : []
            )
          : [],
      reason: outcome === 'playing' ? null : outcome === 'draw' ? 'draw' : 'win',
      winner: outcome === 'one' ? 1 : outcome === 'two' ? 2 : null,
      rematch_ready: [],
    };
  };
  // A coarse public hint: a table played against the computer reads as full,
  // and only a joinable table would carry its round.
  const cabinets = (): CabinetView[] =>
    (Object.keys(CABINET_GAMES) as CabinetId[]).map(cabinet => ({
      cabinet,
      availability: cabinet === CABINET && round !== null ? 'full' : 'empty',
      round_id: null,
      revision: cabinet === CABINET ? revision : 0,
    }));
  function apply(action: string, move: unknown): GameOutcome['result'] {
    switch (action) {
      case 'start_computer':
        if (round !== null) return 'occupied';
        round = roundId(++rounds);
        board = Array<number>(9).fill(0);
        revision++;
        return 'accepted';
      case 'move': {
        if (refusal) {
          const refused = refusal;
          refusal = null;
          return refused;
        }
        const cell =
          record(move) && move.game === 'tic_tac_toe' && typeof move.cell === 'number'
            ? move.cell
            : -1;
        if (result() !== 'playing' || board[cell] !== 0) return 'illegal_move';
        board[cell] = 1;
        const free = board.indexOf(0);
        if (result() === 'playing' && free >= 0) board[free] = 2;
        revision++;
        return 'accepted';
      }
      case 'leave':
        round = null;
        board = Array<number>(9).fill(0);
        revision++;
        return 'accepted';
      default:
        return 'unavailable';
    }
  }
  const authority: WorldCommandAuthority = {
    initial: { cabinets: cabinets() },
    async answer({ type, seq, frame }): Promise<WorldCommandOutcome | undefined> {
      const { action, action_id: actionId } = frame;
      if (type !== 'game' || seq === null) return undefined;
      if (typeof action !== 'string' || typeof actionId !== 'string') return undefined;
      actions.push(action);
      if (action === 'move' && held) {
        const gate = held;
        held = null;
        await gate;
      }
      const subject = round;
      const verdict =
        frame.cabinet !== CABINET
          ? 'unavailable'
          : frame.round_id !== round || frame.expected_revision !== revision
            ? 'conflict'
            : apply(action, frame.move);
      return {
        receipt: {
          seq,
          kind: 'game',
          outcome: { action_id: actionId, result: verdict, round_id: round ?? subject, revision },
        },
        game: game(),
        cabinets: cabinets(),
      };
    },
  };
  return {
    authority,
    actions: () => [...actions],
    current: () => game(),
    /** The next move's answer waits: nothing new may be drawn before it. */
    hold(): () => void {
      let release: () => void = () => undefined;
      held = new Promise<void>(resolve => {
        release = resolve;
      });
      return () => release();
    },
    refuseNextMove(result: GameOutcome['result']) {
      refusal = result;
    },
  };
}

const CABINET_PROP = (() => {
  const id = compileGameCabinets(WORLD).find(item => item.id === CABINET)?.prop;
  const prop = WORLD.props.find(item => item.id === id);
  if (!prop) throw new Error('Missing authored tic-tac-toe cabinet');
  return prop;
})();
const zoneLabel = (id: string) => en.world.zones[id as keyof typeof en.world.zones];

function cellName(index: number, mark: string): string {
  const pieces = en.world.arcade.games.tic_tac_toe;
  return en.world.arcade.cell
    .replace('{{row}}', String(Math.floor(index / 3) + 1))
    .replace('{{column}}', String((index % 3) + 1))
    .replace(
      '{{piece}}',
      mark === 'x' ? pieces.one : mark === 'o' ? pieces.two : en.world.arcade.empty
    );
}
/** The whole board as its accessible names read it: one character per cell. */
async function expectBoard(grid: Locator, marks: string): Promise<void> {
  await expect
    .poll(() =>
      grid
        .getByRole('gridcell')
        .evaluateAll(cells => cells.map(cell => cell.getAttribute('aria-label')))
    )
    .toEqual([...marks].map((mark, index) => cellName(index, mark)));
}
async function openCabinet(page: Page, world?: InertWorld): Promise<Locator> {
  await clickWorldProp(page, CABINET_PROP, zoneLabel);
  // Longer than the link's freshness window: a stalled authority freezes the
  // walk, and the approach resumes when snapshots return.
  if (world) await world.silence(FRESH_SNAPSHOT_MS + 500);
  const dialog = page.getByRole('dialog', { name: TITLE, exact: true });
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  return dialog;
}

for (const [device, viewport] of [
  ['desktop', { width: 1280, height: 900 }],
  ['phone', { width: 390, height: 844 }],
] as const)
  test(`arcade tic-tac-toe against the computer draws server snapshots only (${device})`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const user = await authenticate();
    const desk = ticTacToeDesk(user.id);
    const room = WORLD.zones.find(zone => zone.id === 'multimedia');
    if (!room) throw new Error('Missing authored arcade room');
    const world = await installInertWorldAdmission(page, user.id, {
      spawn: room.arrival,
      commands: desk.authority,
    });
    // The arcade is its own explicit deployment switch, beside the World's.
    await mockApi([
      {
        url: '**/api/v1/config',
        json: {
          ...appConfig,
          features: { ...appConfig.features, world_enabled: true, world_arcade_enabled: true },
        },
      },
    ]);
    await page.goto('/en/dashboard/world');
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');

    const dialog = await openCabinet(page, world);
    const computer = dialog.getByRole('button', { name: en.world.arcade.computer, exact: true });
    // The cabinet only answers an avatar the server placed at its front.
    await expect(computer).not.toHaveAttribute('aria-disabled', 'true');
    expect(desk.actions()).toEqual([]);
    const lobby = await scanPage(page, info, `world-arcade-lobby-${device}`, PANEL);
    expect(lobby.blocking, lobby.summary).toEqual([]);
    await computer.click();

    const grid = dialog.getByRole('grid', { name: TITLE, exact: true });
    const cells = grid.getByRole('gridcell');
    await expectBoard(grid, '.........');
    await expect(
      dialog.getByRole('status').filter({ hasText: en.world.arcade.your_turn })
    ).toBeVisible();
    // Desktop plays through the board's roving focus, the phone by tapping.
    const keyboard = device === 'desktop';
    if (keyboard) await cells.nth(0).focus();
    const play = async (index: number, keys: string[] = []) => {
      const cell = cells.nth(index);
      await expect(cell).not.toHaveAttribute('aria-disabled', 'true');
      if (!keyboard) return cell.click();
      for (const key of keys) await page.keyboard.press(key);
      await expect(cell).toBeFocused();
      await page.keyboard.press('Enter');
    };

    // A move is a request: until the authority answers, nothing is drawn.
    const release = desk.hold();
    await play(0);
    await expect.poll(desk.actions).toEqual(['start_computer', 'move']);
    await expect(
      dialog.getByRole('status').filter({ hasText: en.world.arcade.pending })
    ).toBeVisible();
    await expect(grid).toHaveAttribute('aria-busy', 'true');
    await expectBoard(grid, '.........');
    release();
    await expectBoard(grid, 'xo.......');
    await expect(grid).toHaveAttribute('aria-busy', 'false');

    // A refused move leaves the board as it was and says why.
    desk.refuseNextMove('wrong_turn');
    await play(3, ['ArrowDown']);
    const refused = dialog
      .getByRole('status')
      .filter({ hasText: en.world.arcade.feedback.wrong_turn });
    await expect(refused).toBeVisible();
    await expectBoard(grid, 'xo.......');
    await play(3);
    await expectBoard(grid, 'xoox.....');
    await expect(refused).toHaveCount(0);
    await play(6, ['ArrowDown']);
    await expectBoard(grid, 'xoox..x..');
    await expect(dialog.getByRole('status').filter({ hasText: en.world.arcade.won })).toBeVisible();
    // A finished round offers no move, only another round.
    await expect(grid.locator('[aria-disabled="false"]')).toHaveCount(0);
    await expect(
      dialog.getByRole('button', { name: en.world.arcade.rematch, exact: true })
    ).toBeVisible();
    const finished = await scanPage(page, info, `world-arcade-finished-${device}`, PANEL);
    expect(finished.blocking, finished.summary).toEqual([]);
    await page.screenshot({ path: info.outputPath(`arcade-won-${device}.png`) });

    // Leaving releases the round on the server, and the cabinet is free again.
    await dialog.getByRole('button', { name: en.world.arcade.leave, exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect.poll(() => desk.current()).toBeNull();
    const reopened = await openCabinet(page);
    await expect(
      reopened.getByRole('button', { name: en.world.arcade.computer, exact: true })
    ).not.toHaveAttribute('aria-disabled', 'true');
    await expect(reopened.getByRole('grid')).toHaveCount(0);
    expect(desk.actions()).toEqual(['start_computer', 'move', 'move', 'move', 'move', 'leave']);
    expect(errors).toEqual([]);
  });

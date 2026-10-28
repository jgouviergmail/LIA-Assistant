import { DEFAULT_AVATAR } from '../../src/features/world/avatar-catalogue';
import type { HomeView } from '../../src/features/world/home-protocol';
import { MOVEMENT } from '../../src/features/world/movement';
import { WORLD } from '../../src/features/world/definition';
/** Inert admission for shell/scene ownership tests, never the multiplayer proof. */
import type { PublicActor, WorldView } from '../../src/features/world/protocol';
import type { CabinetView, GameView, GameWaiting } from '../../src/features/world/game-protocol';
import { expect, type Page } from '@playwright/test';
import { idleNotificationStream, registerRoutes } from './api-mock';
import { appConfig } from './dashboard-shell';

/** One command receipt, exactly as the strict wire contract carries it. */
export type WorldReceipt = WorldView['receipts'][number];

/**
 * What one answered command changes in EVERY later snapshot, as the authority's
 * state does: a receipt joins the bounded rolling window the server keeps, and
 * the `you`/game fields persist until a later outcome replaces them. `null` is
 * a value: a cleared pose, a game left.
 */
export interface WorldCommandOutcome {
  receipt?: WorldReceipt;
  /** Merged over the owner's public actor; `position` moves the kinematic echo. */
  you?: Partial<Pick<PublicActor, 'position' | 'facing' | 'pose' | 'emote'>>;
  cabinets?: CabinetView[];
  game?: GameView | null;
  game_request?: GameWaiting | null;
  pose_result?: WorldView['pose_result'];
}

/** A client frame other than `authenticate` and the kinematic `move`. */
export interface WorldCommand {
  readonly type: string;
  /** The controller sequence it consumes; null for heartbeats and control frames. */
  readonly seq: number | null;
  readonly frame: Readonly<Record<string, unknown>>;
}

/**
 * A spec-owned authority for the commands the inert echo never answers (games,
 * poses, gestures). Without one, those commands stay unanswered, as before.
 */
export interface WorldCommandAuthority {
  /** Fields every snapshot carries from the first one (cabinet hints, …). */
  readonly initial?: Omit<WorldCommandOutcome, 'receipt'>;
  /**
   * Answer one command. A returned promise is a slow authority: snapshots keep
   * flowing, and the command's sequence is acknowledged only once it settles.
   */
  answer(
    command: WorldCommand
  ): WorldCommandOutcome | undefined | Promise<WorldCommandOutcome | undefined>;
}

/** The server's `RECEIPT_LIMIT`; the strict client schema refuses a longer list. */
const RECEIPT_WINDOW = 16;

function frameRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/** What a spec can read back from the routed World socket. */
export interface InertWorld {
  /**
   * Authoritative time, not wall time: resolves once the routed socket has sent
   * this many more snapshots. A routed socket emits no `websocket` page event,
   * so the count is kept where the frames are written. A negative assertion
   * made after it covers frames the page was sent, never a guessed delay.
   */
  afterSnapshots(count: number): Promise<void>;
  /**
   * Withhold every snapshot for `ms` without closing the socket, as an
   * authority that stalls; resolves once the next snapshot has been sent.
   */
  silence(ms: number): Promise<void>;
}

export async function enableWorld(page: Page): Promise<void> {
  await registerRoutes(page, [
    {
      url: '**/api/v1/config',
      json: { ...appConfig, features: { ...appConfig.features, world_enabled: true } },
    },
  ]);
}

export async function installInertWorldAdmission(
  page: Page,
  ownerId: string,
  scene: {
    spawn?: { x: number; y: number };
    actors?: PublicActor[];
    /** Optional answers for games, poses and gestures; movement stays the echo. */
    commands?: WorldCommandAuthority;
  } = {}
): Promise<InertWorld> {
  let snapshots = 0;
  let silentUntil = 0;
  await enableWorld(page);
  await registerRoutes(page, [
    {
      url: '**/api/v1/world/experience',
      method: 'GET',
      json: {
        owner_id: ownerId,
        needs_reset: false,
        preferences: {
          version: 1,
          revision: 0,
          show_route: true,
          season_mode: 'calendar',
          hemisphere: 'north',
        },
      },
    },
    {
      url: '**/api/v1/world/avatar',
      method: 'GET',
      json: {
        owner_id: ownerId,
        public_name: 'Explorer',
        needs_setup: true,
        needs_reset: false,
        preferences: { version: 1, revision: 0, appearance: DEFAULT_AVATAR },
      },
    },
    {
      url: '**/api/v1/world/avatar',
      method: 'PUT',
      json: {
        owner_id: ownerId,
        public_name: 'Explorer',
        needs_setup: false,
        needs_reset: false,
        preferences: { version: 1, revision: 1, appearance: DEFAULT_AVATAR },
      },
    },
    // These account-shell calls stay inert; specific journeys may override
    // them after admission. Keep the notification stream genuinely pending.
    { url: '**/api/v1/agents/runs/active', method: 'GET', json: { active: false } },
    { url: '**/api/v1/notifications/broadcasts/unread', method: 'GET', json: { broadcasts: [] } },
    { url: '**/api/v1/habits/presence', method: 'POST', status: 204 },
    {
      url: '**/api/v1/system-settings/debug-panel-status',
      method: 'GET',
      json: { enabled: false, user_access_available: false },
    },
    idleNotificationStream,
    // Normal read-only world shell: unrelated canvas/gesture tests must not
    // exercise the API catch-all's error state or a development error badge.
    {
      url: /\/api\/v1\/workboard\/needs-me(?:\?.*)?$/,
      method: 'GET',
      json: { tickets: [], total: 0 },
    },
    {
      url: '**/api/v1/world/home',
      method: 'GET',
      json: {
        owner_id: ownerId,
        needs_reset: false,
        preferences: { version: 1, revision: 0, palette: 'auto' },
        decoration: {
          automatic_palette: 'clay',
          palette: 'clay',
        },
      } satisfies HomeView,
    },
    {
      url: '**/api/v1/world/environment',
      json: {
        server_time: Date.parse('2026-10-25T12:00:00Z') / 1000,
        timezone: 'UTC',
        weather: null,
      },
    },
    {
      url: '**/api/v1/world/messages/read',
      method: 'POST',
      json: { server_time: Date.now() / 1000, ttl_seconds: 1800, truncated: false, messages: [] },
    },
    {
      url: '**/api/v1/world/ticket',
      json: { account_id: ownerId, version: 1, ticket: 'proof-only-' + 't'.repeat(43) },
    },
  ]);
  await page.routeWebSocket('**/api/v1/world/ws', socket => {
    let pulse: ReturnType<typeof setInterval> | undefined;
    let revision = 0;
    let x = scene.spawn?.x ?? WORLD.spawn.x,
      y = scene.spawn?.y ?? WORLD.spawn.y,
      ack = 0,
      movedAt = Date.now();
    let project: (() => void) | undefined;
    let open = true;
    const authority = scene.commands;
    let receipts: WorldReceipt[] = [];
    let you: Partial<Pick<PublicActor, 'facing' | 'pose' | 'emote'>> = {};
    let world: Omit<WorldCommandOutcome, 'receipt' | 'you'> = {};
    const fold = (outcome: WorldCommandOutcome) => {
      if (outcome.receipt) receipts = [...receipts.slice(-(RECEIPT_WINDOW - 1)), outcome.receipt];
      if (outcome.you) {
        const { position, ...rest } = outcome.you;
        if (position) ({ x, y } = position);
        you = { ...you, ...rest };
      }
      if (outcome.cabinets !== undefined) world = { ...world, cabinets: outcome.cabinets };
      if (outcome.game !== undefined) world = { ...world, game: outcome.game };
      if (outcome.game_request !== undefined)
        world = { ...world, game_request: outcome.game_request };
      if (outcome.pose_result !== undefined) world = { ...world, pose_result: outcome.pose_result };
    };
    if (authority?.initial) fold(authority.initial);
    // A spec's authority answers what the echo does not. Its sequence is
    // consumed once the answer settles, like the server's `actor.seq`.
    const answer = async (frame: Record<string, unknown>, type: string) => {
      if (!authority) return;
      const seq = typeof frame.seq === 'number' ? frame.seq : null;
      const outcome = await authority.answer({ type, seq, frame });
      if (seq !== null) ack = Math.max(ack, seq);
      if (outcome) fold(outcome);
      if (outcome || seq !== null) project?.();
    };
    socket.onMessage(message => {
      const frame: unknown = JSON.parse(String(message));
      if (!frameRecord(frame) || typeof frame.type !== 'string') return;
      if (
        frame.type === 'move' &&
        'seq' in frame &&
        'dx' in frame &&
        'dy' in frame &&
        typeof frame.seq === 'number' &&
        typeof frame.dx === 'number' &&
        typeof frame.dy === 'number'
      ) {
        // Kinematic input echo only. Native SQL/Redis journeys verify real
        // admission, speed limits, collisions and cross-account authority.
        const now = Date.now();
        const dt = Math.min(0.1, Math.max(0, (now - movedAt) / 1000));
        const speed = 'running' in frame && frame.running === true ? MOVEMENT.run : MOVEMENT.walk;
        x += frame.dx * speed * dt;
        y += frame.dy * speed * dt;
        movedAt = now;
        ack = frame.seq;
        project?.();
        return;
      }
      if (frame.type !== 'authenticate') {
        if (frame.type !== 'move') void answer(frame, frame.type);
        return;
      }
      socket.send(
        JSON.stringify({
          type: 'ready',
          version: 2,
          scene: `${WORLD.id}:${WORLD.version}`,
          resume: 'r'.repeat(43),
        })
      );
      project = () => {
        // A slow authority may settle after the page closed its socket.
        if (!open || Date.now() < silentUntil) return;
        snapshots++;
        socket.send(
          JSON.stringify({
            type: 'snapshot',
            version: 2,
            server_time: Date.now() / 1000,
            receipts,
            epoch: '4010c2c2-4bd0-4d21-9c08-b4502db25d72',
            revision: ++revision,
            status: 'active',
            actors: scene.actors ?? [],
            you: {
              id: ownerId,
              alias: 'Explorer',
              position: { x, y },
              facing: 1,
              walking: false,
              ...you,
            },
            ack,
            position: null,
            offer_until: null,
            idle_until: Date.now() / 1000 + 60,
            controlling: true,
            ...world,
          })
        );
      };
      project();
      if (pulse) clearInterval(pulse);
      pulse = setInterval(project, 100);
    });
    socket.onClose(() => {
      open = false;
      if (pulse) clearInterval(pulse);
    });
  });
  return {
    async afterSnapshots(count) {
      const target = snapshots + count;
      await expect.poll(() => snapshots).toBeGreaterThanOrEqual(target);
    },
    async silence(ms) {
      silentUntil = Date.now() + ms;
      await new Promise(resolve => setTimeout(resolve, ms));
      const target = snapshots + 1;
      await expect.poll(() => snapshots).toBeGreaterThanOrEqual(target);
    },
  };
}

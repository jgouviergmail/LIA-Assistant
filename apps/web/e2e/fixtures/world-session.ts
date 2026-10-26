import { DEFAULT_AVATAR } from '../../src/features/world/avatar-catalogue';
import type { HomeView } from '../../src/features/world/home-protocol';
import { MOVEMENT } from '../../src/features/world/movement';
import { WORLD } from '../../src/features/world/definition';
/** Inert admission for shell/scene ownership tests, never the multiplayer proof. */
import type { PublicActor } from '../../src/features/world/protocol';
import type { Page } from '@playwright/test';
import { idleNotificationStream, registerRoutes } from './api-mock';
import { appConfig } from './dashboard-shell';

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
  } = {}
): Promise<void> {
  await enableWorld(page);
  await registerRoutes(page, [
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
    socket.onMessage(message => {
      const frame: unknown = JSON.parse(String(message));
      if (!frame || typeof frame !== 'object' || !('type' in frame)) return;
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
      if (frame.type !== 'authenticate') return;
      socket.send(
        JSON.stringify({
          type: 'ready',
          version: 1,
          scene: `${WORLD.id}:${WORLD.version}`,
          resume: 'r'.repeat(43),
        })
      );
      project = () =>
        socket.send(
          JSON.stringify({
            type: 'snapshot',
            version: 1,
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
            },
            ack,
            position: null,
            offer_until: null,
            idle_until: 1000,
            controlling: true,
          })
        );
      project();
      if (pulse) clearInterval(pulse);
      pulse = setInterval(project, 100);
    });
    socket.onClose(() => {
      if (pulse) clearInterval(pulse);
    });
  });
}

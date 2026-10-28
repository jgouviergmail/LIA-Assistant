/**
 * Hermetic seated-dashboard offer: a seat the World socket confirmed at an
 * eligible table offers the private dashboard. Declining keeps the avatar
 * seated and reads nothing; accepting opens the native dashboard on mocked
 * briefing endpoints with exactly one synthesis. Real seating is proven in
 * `native/world-dashboard.spec.ts`.
 */
import { test, expect } from '../fixtures';
import type { Page } from '@playwright/test';
import { registerRoutes } from '../fixtures/api-mock';
import {
  installInertWorldAdmission,
  type WorldCommandAuthority,
} from '../fixtures/world-session';
import { enterWorld, revealWorldControls } from '../fixtures/world-admission';
import { clickWorldProp } from '../fixtures/world-scene-navigation';
import {
  homeBriefing,
  HOME_GENERATED,
  HOME_ORDER,
  HOME_STATISTICS,
} from '../fixtures/dashboard-home';
import { scanPage } from '../a11y/scan';
import { WORLD } from '../../src/features/world/definition';
import { compilePoseSlots } from '../../src/features/world/pose-slots';
import en from '../../locales/en/translation.json';

const SYNTHESIS = 'INERT hermetic dashboard summary, read only after an explicit acceptance.';
const SEAT = WORLD.props.find(prop => prop.key === 'atrium-n');
const SLOTS = new Map(compilePoseSlots(WORLD).map(slot => [slot.id, slot]));
const SLOT = [...SLOTS.values()].find(slot => slot.prop === SEAT?.id);

/** The server's seating rule for this journey: any authored slot is free. */
function seatDesk() {
  const poses: (string | null)[] = [];
  let seated: string | null = null;
  const authority: WorldCommandAuthority = {
    answer({ type, seq, frame }) {
      if (type !== 'pose' || seq === null) return undefined;
      const slot = typeof frame.slot === 'string' ? SLOTS.get(frame.slot) : undefined;
      if (frame.slot !== null && !slot)
        return { receipt: { seq, kind: 'pose', result: 'invalid' }, pose_result: 'invalid' };
      poses.push(slot?.id ?? null);
      const left = seated ? SLOTS.get(seated) : undefined;
      seated = slot?.id ?? null;
      return {
        receipt: { seq, kind: 'pose', result: 'accepted' },
        pose_result: 'accepted',
        you: slot
          ? { pose: slot.id, position: slot.position, facing: slot.facing }
          : { pose: null, ...(left ? { position: left.approach } : {}) },
      };
    },
  };
  return { authority, poses: () => [...poses], seated: () => seated };
}

/** The dashboard's own reads, answered from the hermetic home fixture and counted. */
async function dashboardReads(page: Page) {
  const briefing = homeBriefing();
  if (briefing.synthesis) briefing.synthesis.text = SYNTHESIS;
  const payloads: Readonly<Record<string, unknown>> = {
    '/briefing/cards': { cards: briefing.cards, windows: briefing.windows },
    '/briefing/synthesis': { greeting: briefing.greeting, synthesis: briefing.synthesis },
    '/briefing/preferences': { hidden: [], order: HOME_ORDER },
    '/chat/users/me/statistics': HOME_STATISTICS,
    '/product/me/results': {
      cycle_start: '2026-10-01',
      useful_results: 37,
      actions: 19,
      automations: 11,
      commitments_closed: 7,
      measured: true,
    },
  };
  await registerRoutes(
    page,
    Object.entries(payloads).map(([path, json]) => ({
      url: new RegExp(`/api/v1${path}(?:\\?.*)?$`),
      method: 'GET',
      json,
    }))
  );
  // Observed where requests leave, mocked or not: a stray briefing read is a 501 too.
  const briefings: string[] = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith('/api/v1/briefing/')) briefings.push(path.replace('/api/v1', ''));
  });
  return briefings;
}
for (const [device, viewport] of [
  ['desktop', { width: 1280, height: 800 }],
  ['phone', { width: 390, height: 844 }],
] as const)
  test(`seated dashboard offer: decline stays seated and reads nothing, accept reads once (${device})`, async ({
    page,
    authenticate,
  }, info) => {
    if (!SEAT || !SLOT) throw new Error('Missing authored atrium seat');
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const unmocked: string[] = [];
    page.on('response', response => {
      if (response.status() === 501) unmocked.push(new URL(response.url()).pathname);
    });
    const user = await authenticate();
    // The account already dismissed its starter checklist, as the home journeys do.
    await registerRoutes(page, [
      {
        url: '**/api/v1/auth/me',
        json: { ...user, onboarding_checklist: { dismissed_at: HOME_GENERATED } },
      },
    ]);
    const desk = seatDesk();
    const world = await installInertWorldAdmission(page, user.id, { commands: desk.authority });
    const briefings = await dashboardReads(page);
    await page.goto('/en/dashboard/world');
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    const before = briefings.length;

    await clickWorldProp(page, SEAT, id => en.world.zones[id as keyof typeof en.world.zones]);
    const offer = page
      .getByRole('dialog', { name: en.world.dashboard.title, exact: true })
      .filter({ hasText: en.world.dashboard.offer });
    await expect(offer).toBeVisible({ timeout: 30_000 });
    expect(desk.poses()).toEqual([SLOT.id]);
    const offered = await scanPage(page, info, `world-dashboard-offer-${device}`, '[role="dialog"]');
    expect(offered.blocking, offered.summary).toEqual([]);

    // Declining is a choice about the dashboard, never about the seat.
    await offer.getByRole('button', { name: en.world.dashboard.stay, exact: true }).click();
    await expect(offer).toHaveCount(0);
    await world.afterSnapshots(10);
    expect(desk.seated()).toBe(SLOT.id);
    expect(desk.poses()).toEqual([SLOT.id]);
    expect(briefings.slice(before)).toEqual([]);

    // The seat keeps its explicit way back to the offer.
    await revealWorldControls(page);
    await page.getByRole('button', { name: en.world.dashboard.title, exact: true }).click();
    await expect(offer).toBeVisible();
    expect(briefings.slice(before)).toEqual([]);
    await offer.getByRole('button', { name: en.world.dashboard.open, exact: true }).click();
    const panel = page.locator('[data-world-native-panel]:visible');
    await expect(panel.getByText(SYNTHESIS, { exact: true })).toBeVisible();
    await expect(
      panel.getByRole('heading', { name: en.dashboard.results.title })
    ).toBeVisible();
    await world.afterSnapshots(10);
    expect(briefings.filter(path => path === '/briefing/synthesis')).toEqual([
      '/briefing/synthesis',
    ]);
    expect(desk.poses()).toEqual([SLOT.id]);
    const opened = await scanPage(
      page,
      info,
      `world-seated-dashboard-${device}`,
      '[data-world-native-panel]'
    );
    expect(opened.blocking, opened.summary).toEqual([]);
    await page.screenshot({ path: info.outputPath(`world-seated-dashboard-${device}.png`) });
    await panel.getByRole('button', { name: en.common.close, exact: true }).click();
    await expect(page.locator('canvas.world-canvas')).toBeFocused();
    expect(desk.seated()).toBe(SLOT.id);
    expect(unmocked).toEqual([]);
    expect(errors).toEqual([]);
  });

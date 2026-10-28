/**
 * Hermetic social gestures: the World socket's receipt, never the press,
 * decides what the scene announces. A gesture the authority refuses announces
 * nothing, and the person is told why. Two independent browsers exchanging a
 * gesture through the real authority are proven in `native/world-emotes.spec.ts`.
 */
import { test, expect } from '../fixtures';
import type { Locator, Page } from '@playwright/test';
import {
  installInertWorldAdmission,
  type WorldCommandAuthority,
  type WorldReceipt,
} from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { scanPage } from '../a11y/scan';
import {
  EMOTES,
  EMOTE_SECONDS,
  type EmoteKind,
} from '../../src/features/world/emote-catalogue';
import en from '../../locales/en/translation.json';

type Verdict = Extract<WorldReceipt, { kind: 'emote' }>['result'];

/** The server's gesture rule for this journey: it answers what the spec decides. */
function gestureDesk() {
  const sent: EmoteKind[] = [];
  let next: Verdict = 'accepted';
  let serial = 0;
  const authority: WorldCommandAuthority = {
    answer({ type, seq, frame }) {
      const kind = EMOTES.find(item => item === frame.emote);
      if (type !== 'emote' || seq === null || !kind) return undefined;
      sent.push(kind);
      const result = next;
      if (result !== 'accepted') return { receipt: { seq, kind: 'emote', result } };
      return {
        receipt: { seq, kind: 'emote', result },
        you: {
          emote: { emote: kind, serial: ++serial, expires_at: Date.now() / 1000 + EMOTE_SECONDS },
        },
      };
    },
  };
  return {
    authority,
    sent: () => [...sent],
    answerNext(result: Verdict) {
      next = result;
    },
  };
}

/** Desktop gestures live in a menu, phone gestures are direct buttons. */
async function gestureSurface(page: Page, phone: boolean): Promise<Locator> {
  if (phone) {
    const group = page.getByRole('group', { name: en.world.emotes.title, exact: true });
    await expect(group).toBeVisible();
    return group;
  }
  await page.getByRole('button', { name: en.world.emotes.title, exact: true }).click();
  const menu = page.getByRole('menu');
  await expect(menu).toBeVisible();
  return menu;
}
async function gesture(page: Page, phone: boolean, kind: EmoteKind): Promise<void> {
  const surface = await gestureSurface(page, phone);
  const name = en.world.emotes[kind];
  await (phone
    ? surface.getByRole('button', { name, exact: true })
    : surface.getByRole('menuitem', { name: new RegExp(`^${name}\\b`) })
  ).click();
  // A gesture hands the keyboard back to the scene it was made in.
  await expect(page.locator('canvas.world-canvas')).toBeFocused();
}

for (const [device, viewport] of [
  ['desktop', { width: 1280, height: 900 }],
  ['phone', { width: 390, height: 844 }],
] as const)
  test(`a gesture is announced from its server receipt, a refusal is told, never announced (${device})`, async ({
    page,
    authenticate,
  }, info) => {
    await page.setViewportSize(viewport);
    const phone = device === 'phone';
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const user = await authenticate();
    const desk = gestureDesk();
    const world = await installInertWorldAdmission(page, user.id, { commands: desk.authority });
    await page.goto('/en/dashboard/world');
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    const announced = (kind: EmoteKind) =>
      page.locator(`[data-world-emote="${kind}"][data-world-emote-actor="${user.id}"]`);

    const surface = await gestureSurface(page, phone);
    const scan = await scanPage(
      page,
      info,
      `world-gestures-${device}`,
      phone ? '.world-emote-buttons' : '[role="menu"]'
    );
    expect(scan.blocking, scan.summary).toEqual([]);
    if (!phone) {
      await page.keyboard.press('Escape');
      await expect(surface).toBeHidden();
    }

    const feedback = page.locator('[data-world-emote-feedback]');
    await gesture(page, phone, 'wave');
    await expect.poll(desk.sent).toEqual(['wave']);
    // One translated sentence names who made which gesture.
    await expect(announced('wave')).toHaveText(
      en.world.emotes.announcements.wave.replace('{{alias}}', 'Explorer')
    );
    await expect(feedback.filter({ hasText: /\S/ })).toHaveCount(0);
    await page.screenshot({ path: info.outputPath(`world-gesture-${device}.png`) });
    // The server's deadline ends the gesture; nothing replays it.
    await expect(announced('wave')).toHaveCount(0);

    // Past the interval the page sends again; the authority's refusal wins,
    // announces nothing and is said to the person.
    desk.answerNext('rate_limited');
    await gesture(page, phone, 'thanks');
    await expect.poll(desk.sent).toEqual(['wave', 'thanks']);
    const sentence = page.locator('[data-world-emote-feedback="rate_limited"] p');
    await expect(sentence).toHaveText(en.world.emotes.rate_limited);
    await expect(sentence).toBeVisible();
    // Said through a live status region, not only drawn.
    await expect(
      page.getByRole('status').filter({ hasText: en.world.emotes.rate_limited })
    ).toHaveCount(1);
    const serverRefusal = await sentence.elementHandle();

    // Inside the interval the page refuses on its own: nothing is sent, and the
    // refusal is said again, as a new announcement.
    await gesture(page, phone, 'laugh');
    await expect.poll(() => serverRefusal?.evaluate(node => node.isConnected)).toBe(false);
    await expect(sentence).toHaveText(en.world.emotes.rate_limited);
    await world.afterSnapshots(5);
    expect(desk.sent()).toEqual(['wave', 'thanks']);
    for (const kind of ['thanks', 'laugh'] as const) await expect(announced(kind)).toHaveCount(0);
    expect(errors).toEqual([]);
  });

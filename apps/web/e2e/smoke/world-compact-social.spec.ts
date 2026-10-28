/** Hermetic proximity, draft ownership and actual responsive hit targets. */
import { test, expect } from '../fixtures';
import type { Locator, Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { WORLD } from '../../src/features/world/definition';
import type { PublicActor } from '../../src/features/world/protocol';
import type { WorldMailbox } from '../../src/features/world/message-protocol';
import { cssPixels } from '../native/layout';
import en from '../../locales/en/translation.json';

const PEER = '5010c2c2-4bd0-4d21-9c08-b4502db25001';
const viewports = [
  { width: 390, height: 844 },
  { width: 320, height: 568 },
  { width: 568, height: 320 },
  { width: 1280, height: 900 },
];

function mailbox(ownerId: string): WorldMailbox {
  const now = Date.now() / 1000;
  const shared = {
    sender_id: PEER,
    sender_alias: 'Camille',
    outgoing: false,
    language: 'en' as const,
    status: 'original' as const,
    created_at: now,
    expires_at: now + 1800,
    receipt: null,
  };
  return {
    server_time: now,
    ttl_seconds: 1800,
    truncated: false,
    public_truncated: false,
    public_available: true,
    messages: [
      {
        ...shared,
        id: '5010c2c2-4bd0-4d21-9c08-b4502db25002',
        recipient_id: ownerId,
        recipient_alias: 'Explorer',
        original: 'A private hello',
        text: 'A private hello',
      },
    ],
    public_messages: [
      {
        ...shared,
        id: '5010c2c2-4bd0-4d21-9c08-b4502db25003',
        audience: 'public',
        original: 'Hello everyone in the world',
        text: 'Hello everyone in the world',
      },
    ],
  };
}

async function selectedLabel(select: Locator): Promise<string> {
  return select.locator('option:checked').innerText();
}

async function verifyControlGeometry(page: Page, compact: boolean): Promise<void> {
  const steady = [
    '.world-compact-chat',
    '[data-world-conversations]',
    ...(compact ? ['.world-joystick', '.world-emote-buttons > button'] : []),
  ];
  // LIA roams, so the nearby action comes and goes: it is measured in the same
  // DOM snapshot as the others, never addressed by its rank in a live list
  // (that rank waited for LIA's return, ~28 s, whenever she walked away).
  const selectors = [...steady, ...(compact ? ['.world-nearby-action'] : [])];
  for (const control of await page.locator(steady.join(', ')).filter({ visible: true }).all()) {
    if (!(await control.evaluate(element => element.classList.contains('world-compact-chat'))))
      await control.click({ trial: true, timeout: 5000 });
  }
  const controls = page.locator(selectors.join(', ')).filter({ visible: true });
  const geometry = await controls.evaluateAll(elements => {
    const scene = document.querySelector('.world-prototype');
    if (!scene) throw new Error('Missing world scene');
    const bounds = scene.getBoundingClientRect();
    return {
      bounds: { left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom },
      boxes: elements.map(element => {
        const box = element.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return {
          name: element.getAttribute('aria-label') ?? element.className,
          left: box.left,
          top: box.top,
          right: box.right,
          bottom: box.bottom,
          width: box.width,
          height: box.height,
          reachable:
            element.classList.contains('world-compact-chat') || (!!hit && element.contains(hit)),
        };
      }),
    };
  });
  for (const [index, box] of geometry.boxes.entries()) {
    expect(cssPixels(box.width), box.name).toBeGreaterThanOrEqual(44);
    expect(cssPixels(box.height), box.name).toBeGreaterThanOrEqual(44);
    expect(box.reachable, `${box.name} is covered`).toBe(true);
    expect(box.left, box.name).toBeGreaterThanOrEqual(geometry.bounds.left - 1);
    expect(box.top, box.name).toBeGreaterThanOrEqual(geometry.bounds.top - 1);
    expect(box.right, box.name).toBeLessThanOrEqual(geometry.bounds.right + 1);
    expect(box.bottom, box.name).toBeLessThanOrEqual(geometry.bounds.bottom + 1);
    for (const other of geometry.boxes.slice(index + 1)) {
      const overlap =
        Math.min(box.right, other.right) - Math.max(box.left, other.left) > 1 &&
        Math.min(box.bottom, other.bottom) - Math.max(box.top, other.top) > 1;
      expect(overlap, `${box.name} overlaps ${other.name}`).toBe(false);
    }
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const viewport of viewports) {
  test(`compact social chat preserves audience and reachable controls at ${viewport.width}x${viewport.height}`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize(viewport);
    const compact = viewport.width < 768 || viewport.height <= 520;
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const user = await authenticate();
    const peer: PublicActor = {
      id: PEER,
      alias: 'Camille',
      position: { x: WORLD.spawn.x + 1, y: WORLD.spawn.y },
      facing: 1,
      walking: false,
    };
    await installInertWorldAdmission(page, user.id, { actors: [peer] });
    await mockApi([{ url: '**/api/v1/world/messages/read', json: mailbox(user.id) }]);
    await page.goto('/en/dashboard/world');
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    const quick = page.getByRole('region', { name: en.world.compact.title, exact: true });
    const recipient = quick.getByRole('combobox', { name: en.world.compact.destination });
    const launcher = page.getByRole('button', { name: en.world.messages.action, exact: true });
    if (compact) {
      await expect(quick).toBeHidden();
      await expect(page.locator('.world-emote-buttons > button')).toHaveCount(6);
      await verifyControlGeometry(page, true);
      await page.screenshot({
        path: info.outputPath(`compact-social-${viewport.width}-hidden.png`),
      });
      const worldControls = page.getByRole('button', { name: en.world.controls, exact: true });
      await worldControls.click();
      await expect(worldControls).toHaveAttribute('aria-expanded', 'true');
      await launcher.click();
      await expect(worldControls).toHaveAttribute('aria-expanded', 'false');
      await expect(page.locator('.world-prototype')).toHaveAttribute('data-hud-expanded', 'false');
    }
    await expect(quick).toBeVisible();
    await expect.poll(() => selectedLabel(recipient)).toBe('Auto · Private · Camille');
    await expect(quick.getByRole('log')).toContainText('A private hello');
    if (compact) {
      await expect(page.locator('.world-emote-buttons > button')).toHaveCount(6);
      await expect(page.locator('.world-joystick')).toBeVisible();
    }
    await verifyControlGeometry(page, compact);
    await page.screenshot({
      path: info.outputPath(`compact-social-${viewport.width}-private.png`),
    });

    const field = quick.getByRole('textbox', { name: en.world.messages.message, exact: true });
    await field.fill('This draft stays private');
    if (compact) {
      await quick.getByRole('button', { name: en.world.compact.hide }).click();
      await expect(quick.getByRole('log')).toBeHidden();
      await expect(field).toHaveValue('This draft stays private');
      await quick.getByRole('button', { name: en.world.compact.show }).click();
      await expect(quick.getByRole('log')).toBeVisible();
      await quick.getByRole('button', { name: en.world.compact.close, exact: true }).click();
      await expect(quick).toBeHidden();
      await launcher.click();
      await expect(quick).toBeVisible();
      await expect(field).toHaveValue('This draft stays private');
    }
    peer.position = { x: WORLD.spawn.x + 5, y: WORLD.spawn.y };
    await quick.getByRole('button', { name: en.world.compact.expand }).click();
    const full = page.locator('[data-world-messages]');
    await expect(full).toBeVisible();
    await expect(full.getByRole('textbox', { name: en.world.messages.message })).toHaveValue(
      'This draft stays private'
    );
    await expect(full.getByRole('heading', { name: 'Camille', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(quick).toBeVisible();
    await expect(field).toHaveValue('This draft stays private');
    await expect.poll(() => selectedLabel(recipient)).toBe('Auto · Private · Camille');
    await field.fill('');
    await page.locator('canvas.world-canvas').focus();
    await expect
      .poll(() => selectedLabel(recipient))
      .toBe(`Auto · Public · ${en.world.public.title}`);
    await expect(quick.getByRole('log')).toContainText('Hello everyone in the world');
    await verifyControlGeometry(page, compact);
    await page.screenshot({ path: info.outputPath(`compact-social-${viewport.width}-public.png`) });
    if (!compact) {
      const spacing = await page.locator('.world-sky-badge').evaluate(element => {
        const next = element.nextElementSibling;
        return next ? next.getBoundingClientRect().top - element.getBoundingClientRect().bottom : 0;
      });
      expect(spacing).toBeGreaterThanOrEqual(7);
    }
    expect(errors).toEqual([]);
  });
}

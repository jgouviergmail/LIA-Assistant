/** Connexions LIA: independent consents, explicit search and responsive reading. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page } from '@playwright/test';
import {
  test,
  expect,
  waitForHydration,
  idleNotificationStream,
  waitForMockGate,
} from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

// Complete /peers REST fixture; importing its hook here would pull JSX into the Node-only E2E tsconfig.
type ShareItem = { domain: 'calendar' | 'task'; level: 'availability' | 'details' | 'titles' };
interface ConnectionView {
  id: string;
  peer_id: string;
  peer_display_name: string;
  peer_email_hint: string;
  peer_email: string | null;
  status: 'accepted' | 'pending';
  direction: 'incoming' | 'outgoing' | null;
  requested_at: string;
  responded_at: string | null;
  context_message: string | null;
  my_shares: ShareItem[];
  their_shares: ShareItem[];
}

const translations: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
function copy(key: string): string {
  let value: unknown = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing label: ${key}`);
  return value;
}
function connection(overrides: Partial<ConnectionView> = {}): ConnectionView {
  return {
    id: '00000000-0000-4000-8000-000000000102',
    peer_id: '00000000-0000-4000-8000-000000000202',
    peer_display_name: 'Alexandre Saint-Germain de Montparnasse',
    peer_email_hint: 'a•••@example.test',
    peer_email: 'alexandre.saint-germain.de.montparnasse@example.test',
    status: 'accepted',
    direction: null,
    requested_at: '2026-10-12T08:00:00Z',
    responded_at: '2026-10-12T09:00:00Z',
    context_message: null,
    my_shares: [{ domain: 'calendar', level: 'availability' }],
    their_shares: [{ domain: 'calendar', level: 'details' }],
    ...overrides,
  };
}
const section = (page: Page) => page.locator('#settings-section-peer-connections');
const fold = (page: Page, key: string) =>
  section(page)
    .locator('summary')
    .filter({ hasText: copy(key) });
async function measure(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}
const observed = new WeakMap<Page, { api: string[]; errors: string[]; google: string[] }>();
test.beforeEach(async ({ page, context, baseURL }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    )
  );
  if (baseURL)
    await context.addCookies([
      {
        name: 'lia_session',
        value: 'e2e-session',
        url: new URL(baseURL).origin,
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  const events = { api: [] as string[], errors: [] as string[], google: [] as string[] };
  observed.set(page, events);
  page.on('response', response => {
    if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/v1/'))
      events.api.push(response.url());
  });
  page.on('pageerror', error => events.errors.push(error.message));
  context.on('request', request => {
    if (
      ['www.google.com', 'content-autofill.googleapis.com'].includes(
        new URL(request.url()).hostname
      )
    )
      events.google.push(request.url());
  });
});
test.afterEach(async ({ page, apiNetworkGuard }, info) => {
  const events = observed.get(page)!;
  await info.attach('network-isolation.json', {
    body: JSON.stringify({ ...events, blocked: apiNetworkGuard.blockedRequests }),
    contentType: 'application/json',
  });
  expect(events.api, 'all application API operations are explicitly mocked').toEqual([]);
  expect(events.errors, 'no uncaught browser error').toEqual([]);
  expect(events.google, 'no page or worker Google request').toEqual([]);
  const browserOnly = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(apiNetworkGuard.blockedRequests.filter(request => !browserOnly.has(request))).toEqual([]);
});

for (const [width, theme] of [
  [1440, 'light'],
  [320, 'oled'],
] as const) {
  test(`${width}px ${theme}: separate controls, explicit discovery, retained consent and confirmed removal`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await prepareTheme(page, theme);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await authenticate({ language: 'fr', theme, font_size: width === 320 ? 20 : 16 });
    const peer = connection();
    const pending = connection({
      id: '00000000-0000-4000-8000-000000000103',
      peer_id: '00000000-0000-4000-8000-000000000203',
      peer_display_name: 'Nora Exemple',
      peer_email: null,
      peer_email_hint: 'n•••@example.test',
      status: 'pending',
      direction: 'incoming',
      responded_at: null,
      context_message: '<script>Une demande reste du texte, sans exécution.</script>',
      my_shares: [],
      their_shares: [],
    });
    let currentConnections = [
      peer,
      connection({
        id: '00000000-0000-4000-8000-000000000104',
        peer_id: '00000000-0000-4000-8000-000000000204',
        peer_display_name: 'Camille Exemple',
        peer_email: null,
        peer_email_hint: 'c•••@example.test',
      }),
    ];
    const shares: unknown[] = [],
      searches: unknown[] = [],
      requests: unknown[] = [];
    let deletes = 0,
      readsAvailable = width !== 320,
      readCount = 0;
    let finishShare: () => void = () => undefined;
    const shareGate = new Promise<void>(resolve => {
      finishShare = resolve;
    });
    await mockApi([
      {
        url: '**/api/v1/config',
        method: 'GET',
        json: { ...appConfig, features: { ...appConfig.features, peers_enabled: true } },
      },
      { url: '**/api/v1/notifications/broadcasts/unread', method: 'GET', json: { broadcasts: [] } },
      { url: '**/api/v1/agents/runs/active', method: 'GET', json: { active: false } },
      {
        url: '**/api/v1/system-settings/debug-panel-status',
        method: 'GET',
        json: { enabled: false, user_access_available: false },
      },
      {
        url: '**/api/v1/habits/presence',
        method: 'POST',
        handler: route => route.fulfill({ status: 204, body: '' }),
      },
      idleNotificationStream,
      {
        url: '**/api/v1/peers/me',
        method: 'GET',
        handler: route =>
          route.fulfill({ json: { discovery_enabled: true, email_visible: false } }),
      },
      { url: '**/api/v1/peers/requests', method: 'GET', json: [pending] },
      {
        url: '**/api/v1/peers/connections',
        method: 'GET',
        handler: route => {
          readCount += 1;
          return readsAvailable
            ? route.fulfill({ json: currentConnections })
            : route.fulfill({ status: 503, json: { detail: 'unavailable' } });
        },
      },
      {
        url: '**/api/v1/peers/blocks',
        method: 'GET',
        json: [
          {
            blocked_id: '00000000-0000-4000-8000-000000000205',
            blocked_display_name: 'Sam Exemple',
            created_at: '2026-10-01T10:00:00Z',
          },
        ],
      },
      {
        url: '**/api/v1/peers/access-log',
        method: 'GET',
        json: [
          {
            accessor_display_name: 'Alexandre Saint-Germain de Montparnasse',
            domain: 'calendar',
            tool_name: 'get_peer_availability',
            created_at: '2026-10-16T08:30:00Z',
          },
        ],
      },
      {
        url: '**/api/v1/peers/discovery/search',
        method: 'POST',
        handler: route => {
          searches.push(route.request().postDataJSON());
          return route.fulfill({
            json: [
              {
                peer_id: '00000000-0000-4000-8000-000000000206',
                display_name: 'Sophie Exemple',
                email_hint: 's•••@example.test',
                relationship: 'none',
              },
            ],
          });
        },
      },
      {
        url: '**/api/v1/peers/requests',
        method: 'POST',
        handler: route => {
          requests.push(route.request().postDataJSON());
          return route.fulfill({ json: { status: 'pending' } });
        },
      },
      {
        url: '**/api/v1/peers/connections/*/shares',
        method: 'PUT',
        handler: async (route, signal) => {
          const body = route.request().postDataJSON() as { domain: 'task'; level: 'titles' | null };
          shares.push(body);
          if (shares.length === 1 && !(await waitForMockGate(shareGate, signal))) return;
          if (width === 320 && shares.length === 1)
            return route.fulfill({ status: 409, json: { detail: 'peers_conflict' } });
          const next: ShareItem[] = [
            ...peer.my_shares.filter(item => item.domain !== body.domain),
            ...(body.level ? [{ domain: body.domain, level: body.level }] : []),
          ];
          currentConnections = currentConnections.map(item =>
            item.id === peer.id ? { ...item, my_shares: next } : item
          );
          return route.fulfill({ json: {} });
        },
      },
      {
        url: '**/api/v1/peers/connections/*',
        method: 'DELETE',
        handler: route => {
          deletes += 1;
          currentConnections = currentConnections.filter(item => item.id !== peer.id);
          return route.fulfill({ status: 204, body: '' });
        },
      },
    ]);
    const response = await page.goto('/fr/dashboard/settings?section=peer-connections');
    expect(response?.status()).toBe(200);
    await waitForHydration(page, '#settings-section-peer-connections');
    if (width === 320) {
      await expect(section(page).getByRole('alert')).toContainText(
        copy('settings.peers.load_error')
      );
      await expect(
        section(page).getByText(copy('settings.peers.connections.empty'), { exact: true })
      ).toHaveCount(0);
      readsAvailable = true;
      await section(page)
        .getByRole('button', { name: copy('common.retry'), exact: true })
        .click();
    }
    const search = section(page).getByRole('textbox', {
      name: copy('settings.peers.discovery.search_label'),
      exact: true,
    });
    await expect(search).toBeVisible();
    await expect.poll(() => readCount).toBeGreaterThanOrEqual(width === 320 ? 2 : 1);
    await expect(section(page)).not.toContainText(/settings\.peers\.[a-z_]+/);
    const commands = [
      'settings.peers.visibility_title',
      'settings.peers.blocks.title',
      'settings.peers.access_log.title',
    ];
    const boxes = [];
    for (const key of commands) {
      const control = fold(page, key);
      await expect(control).toBeVisible();
      await expect(control.locator('..')).not.toHaveAttribute('open', '');
      boxes.push(await measure(control));
    }
    expect(boxes[1].y).toBeGreaterThanOrEqual(boxes[0].y + boxes[0].height - 1);
    expect(boxes[2].y).toBeGreaterThanOrEqual(boxes[1].y + boxes[1].height - 1);
    const searchButton = section(page).getByRole('button', {
      name: copy('settings.peers.discovery.search_button'),
      exact: true,
    });
    const inputBox = await measure(search),
      buttonBox = await measure(searchButton);
    expect(buttonBox.y).toBeGreaterThanOrEqual(inputBox.y + inputBox.height);
    await expect(fold(page, 'settings.peers.requests.title').locator('..')).not.toHaveAttribute(
      'open',
      ''
    );
    await expect(section(page).getByRole('combobox')).toHaveCount(0);
    await search.fill('  Sophie Exemple  ');
    expect(searches).toHaveLength(0);
    await search.press('Enter');
    await expect(section(page).getByText('Sophie Exemple', { exact: true })).toBeVisible();
    expect(searches).toEqual([{ query: 'Sophie Exemple' }]);
    await section(page)
      .getByRole('textbox', { name: copy('settings.peers.discovery.context_label'), exact: true })
      .fill('  Notre atelier de vendredi.  ');
    await section(page)
      .getByRole('button', { name: copy('settings.peers.discovery.request_button'), exact: true })
      .click();
    await expect(search).toHaveValue('');
    expect(requests).toEqual([
      {
        peer_id: '00000000-0000-4000-8000-000000000206',
        context_message: 'Notre atelier de vendredi.',
      },
    ]);
    await search.fill('Recherche conservée');
    const identity = section(page).getByRole('button').filter({ hasText: peer.peer_display_name });
    await identity.focus();
    await page.keyboard.press('Enter');
    await expect(identity).toHaveAttribute('aria-expanded', 'true');
    const mine = section(page).getByRole('region', {
      name: copy('settings.peers.shares.my_title'),
      exact: true,
    });
    const theirs = section(page).getByRole('region', {
      name: copy('settings.peers.shares.their_named_title').replace(
        '{{name}}',
        peer.peer_display_name
      ),
      exact: true,
    });
    const mineBox = await measure(mine),
      theirsBox = await measure(theirs);
    if (width > 1000) {
      expect(Math.abs(mineBox.y - theirsBox.y)).toBeLessThan(2);
      expect(mineBox.x).toBeGreaterThanOrEqual(theirsBox.x + theirsBox.width);
    } else expect(mineBox.y).toBeGreaterThan(theirsBox.y);
    await expect(theirs.getByRole('switch')).toHaveCount(0);
    await expect(
      theirs.getByText(copy('settings.peers.shares.calendar_level.details'), { exact: true })
    ).toBeVisible();
    const task = mine.getByRole('switch', {
      name: copy('settings.peers.shares.task_label'),
      exact: true,
    });
    await task.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => shares.length).toBe(1);
    await expect(task).toHaveAttribute('aria-disabled', 'true');
    await expect(task).toBeFocused();
    await page.keyboard.press('Enter');
    expect(shares).toHaveLength(1);
    finishShare();
    if (width === 320) {
      await expect(
        page.getByText(copy('settings.peers.errors.conflict'), { exact: true })
      ).toBeVisible();
      await expect(task).not.toBeChecked();
      await expect(task).toHaveAttribute('aria-disabled', 'false');
      await task.press('Enter');
    }
    await expect(task).toBeChecked();
    await expect(task).toBeFocused();
    await expect(search).toHaveValue('Recherche conservée');
    await fold(page, 'settings.peers.requests.title').click();
    await expect(section(page).getByText(pending.context_message!, { exact: true })).toBeVisible();
    await expect(
      page.locator('script').filter({ hasText: 'Une demande reste du texte' })
    ).toHaveCount(0);
    await fold(page, 'settings.peers.access_log.title').click();
    await expect(section(page).locator('time')).toHaveAttribute('datetime', '2026-10-16T08:30:00Z');
    await expectNoOverflow(page, `Connexions ${width}px ${theme}, expanded and long identities`);
    const image = info.outputPath(`peer-connections-${width}-${theme}.png`);
    await page.screenshot({ path: image, fullPage: true });
    await info.attach(`peer-connections-${width}-${theme}`, {
      path: image,
      contentType: 'image/png',
    });
    const audit = await scanPage(page, info, `peer-connections-${width}-${theme}`);
    expect(audit.blocking, audit.summary).toHaveLength(0);
    await section(page)
      .getByRole('button', { name: copy('settings.peers.connections.remove'), exact: true })
      .click();
    await page
      .getByRole('alertdialog')
      .getByRole('button', { name: copy('common.cancel'), exact: true })
      .click();
    expect(deletes).toBe(0);
    await expect(identity).toBeVisible();
    await section(page)
      .getByRole('button', { name: copy('settings.peers.connections.remove'), exact: true })
      .click();
    await page
      .getByRole('alertdialog')
      .getByRole('button', { name: copy('common.confirm'), exact: true })
      .click();
    await expect(identity).toHaveCount(0);
    expect(deletes).toBe(1);
    await expect(section(page).locator('#peers-connections-title')).toBeFocused();
    await expect(section(page).getByText('Camille Exemple', { exact: true })).toBeVisible();
  });
}

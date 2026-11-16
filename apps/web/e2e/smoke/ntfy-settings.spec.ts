/** ntfy in the notification settings: reading, subscribing a device, a refusal, at two widths. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Page } from '@playwright/test';
import { test, expect, waitForHydration, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

// The /notifications/ntfy fixtures; importing the hook's types would pull JSX into the Node tsconfig.
interface View {
  id: string;
  server_kind: 'instance' | 'custom';
  server_url: string;
  topic: string | null;
  has_token: boolean;
  content: 'minimal' | 'full';
  is_active: boolean;
  last_sent_at: string | null;
  last_error_code: string | null;
  last_error_at: string | null;
  created_at: string;
  subscribe_link: string | null;
}

const translations: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
function copy(key: string, values: Record<string, string> = {}): string {
  let value: unknown = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing label: ${key}`);
  return Object.entries(values).reduce(
    (text, [name, replacement]) => text.replace(`{{${name}}}`, replacement),
    value
  );
}
const ntfy = (key: string, values?: Record<string, string>) =>
  copy(`settings.notifications.ntfy.${key}`, values);

function view(overrides: Partial<View>): View {
  return {
    id: '00000000-0000-4000-8000-000000000301',
    server_kind: 'instance',
    server_url: 'https://ntfy.example.test',
    topic: 'lia_AbCdEfGhIjKlMnOpQrStUvWxYz12',
    has_token: false,
    content: 'minimal',
    is_active: true,
    last_sent_at: '2026-11-15T08:00:00Z',
    last_error_code: null,
    last_error_at: null,
    created_at: '2026-11-10T08:00:00Z',
    subscribe_link: 'ntfy://ntfy.example.test/lia_AbCdEfGhIjKlMnOpQrStUvWxYz12?display=LIA',
    ...overrides,
  };
}

const LONG_HOST = 'notifications.un-serveur-au-nom-particulierement-long.example.test';
const REFUSED = view({
  id: '00000000-0000-4000-8000-000000000302',
  server_kind: 'custom',
  server_url: `https://${LONG_HOST}`,
  topic: 'mes-alertes-personnelles',
  content: 'full',
  is_active: false,
  last_sent_at: null,
  last_error_code: 'auth_refused',
  last_error_at: '2026-11-16T07:00:00Z',
  subscribe_link: `ntfy://${LONG_HOST}/mes-alertes-personnelles?display=LIA`,
});
const CREATED = view({
  id: '00000000-0000-4000-8000-000000000303',
  topic: 'lia_ZyXwVuTsRqPoNmLkJiHgFeDcBa98',
  last_sent_at: null,
  subscribe_link: 'ntfy://ntfy.example.test/lia_ZyXwVuTsRqPoNmLkJiHgFeDcBa98?display=LIA',
});
// A 1×1 transparent PNG: the code itself is drawn by the API, never by the page.
const QR =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

const block = (page: Page) =>
  page
    .locator('#settings-section-notifications section')
    .filter({ has: page.getByRole('heading', { name: ntfy('title') }) });

for (const [width, theme] of [
  [1280, 'light'],
  [360, 'dark'],
] as const) {
  test(`${width}px ${theme}: subscriptions read, a device subscribed, a refusal said`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await prepareTheme(page, theme);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await authenticate({ language: 'fr', theme });
    let subscriptions: View[] = [view({}), REFUSED];
    const posted: unknown[] = [];
    let refuseNext = false;
    await mockApi([
      {
        url: '**/api/v1/config',
        method: 'GET',
        json: {
          ...appConfig,
          features: { ...appConfig.features, ntfy_enabled: true },
          capabilities: { ntfy: { enabled: true, family: 'reach' } },
        },
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
      { url: '**/api/v1/notifications/tokens', method: 'GET', json: { tokens: [] } },
      {
        url: '**/api/v1/notifications/ntfy',
        method: 'GET',
        handler: route =>
          route.fulfill({
            json: {
              instance_url: 'https://ntfy.example.test',
              custom_servers_enabled: true,
              max_subscriptions: 3,
              subscriptions,
            },
          }),
      },
      {
        url: '**/api/v1/notifications/ntfy',
        method: 'POST',
        handler: route => {
          posted.push(route.request().postDataJSON());
          if (refuseNext) {
            return route.fulfill({ status: 422, json: { detail: { code: 'ntfy_topic_invalid' } } });
          }
          subscriptions = [...subscriptions, CREATED];
          return route.fulfill({ status: 201, json: CREATED });
        },
      },
      {
        url: `**/api/v1/notifications/ntfy/${CREATED.id}/qr`,
        method: 'GET',
        json: { qr_data_uri: QR },
      },
    ]);

    await page.goto('/fr/dashboard/settings?section=notifications');
    await waitForHydration(page, '#settings-section-notifications');
    const ntfyBlock = block(page);
    await expect(ntfyBlock.getByRole('heading', { name: ntfy('title') })).toBeVisible();

    // What the API reports, in words: the server, the pause, why the last publication failed.
    const rows = ntfyBlock.getByRole('listitem');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).getByText(ntfy('server_instance'))).toBeVisible();
    await expect(rows.nth(1).getByText(LONG_HOST)).toBeVisible();
    await expect(rows.nth(1).getByText(ntfy('paused'))).toBeVisible();
    await expect(
      rows.nth(1).getByText(ntfy('last_error', { reason: ntfy('outcome.auth_refused') }))
    ).toBeVisible();
    await expectNoOverflow(page, `ntfy ${width} list`);

    // Check configuration notices while visible, before a dialog makes them inert.
    const listAudit = await scanPage(page, info, `ntfy-list-${width}-${theme}`);
    expect(listAudit.blocking, listAudit.summary).toHaveLength(0);

    // A refusal keeps the form open and says, in words, what to correct.
    refuseNext = true;
    await ntfyBlock.getByRole('button', { name: ntfy('add') }).click();
    const form = page.getByRole('dialog', { name: ntfy('form.title') });
    await form.getByRole('radio', { name: ntfy('form.server_custom') }).check();
    await form.getByLabel(ntfy('form.server_url')).fill('https://ntfy.sh');
    await form.getByLabel(ntfy('form.topic')).fill('mes alertes');
    await form.getByRole('button', { name: ntfy('form.submit') }).click();
    await expect(form.getByRole('alert')).toHaveText(ntfy('refusal.ntfy_topic_invalid'));
    await expect(form.getByLabel(ntfy('form.server_url'))).toHaveValue('https://ntfy.sh');

    // On the instance's server, nothing to type: the device dialog follows.
    refuseNext = false;
    await form.getByRole('radio', { name: ntfy('form.server_instance') }).check();
    await form.getByRole('button', { name: ntfy('form.submit') }).click();
    const device = page.getByRole('dialog', { name: ntfy('device.title') });
    await expect(device.getByRole('img', { name: ntfy('device.qr_alt') })).toBeVisible();
    await expect(device.getByRole('link', { name: ntfy('device.open_app') })).toHaveAttribute(
      'href',
      CREATED.subscribe_link ?? ''
    );
    await expect(
      device.getByRole('textbox', { name: ntfy('device.topic'), exact: true })
    ).toHaveValue(CREATED.topic ?? '');
    expect(posted).toEqual([
      { server: 'custom', server_url: 'https://ntfy.sh', topic: 'mes alertes', content: 'minimal' },
      { server: 'instance', content: 'minimal' },
    ]);
    await expectNoOverflow(page, `ntfy ${width} device dialog`);

    const image = info.outputPath(`ntfy-${width}-${theme}.png`);
    await page.screenshot({ path: image, fullPage: true });
    await info.attach(`ntfy-${width}-${theme}`, { path: image, contentType: 'image/png' });
    const audit = await scanPage(page, info, `ntfy-device-${width}-${theme}`);
    expect(audit.blocking, audit.summary).toHaveLength(0);

    // Closed, the list holds the new subscription and the keyboard is back on the page.
    await device.getByRole('button', { name: ntfy('device.done') }).click();
    await expect(device).toBeHidden();
    await expect(ntfyBlock.getByRole('listitem')).toHaveCount(3);
  });
}

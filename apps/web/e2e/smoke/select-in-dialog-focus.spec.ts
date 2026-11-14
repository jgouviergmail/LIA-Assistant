/**
 * A list inside a dialog: it takes the keyboard, and the selection bubble never freezes it.
 *
 * Measured 2026-11-13 on the MCP server form: with two copies of Radix's focus-scope module
 * (the Select of one release beside the Dialog of the next), the dialog's trap sent the
 * focus back out of every open list, so no option could be chosen from the keyboard; and
 * once the dictation or selection bubble had paused that trap, the two traps sent the
 * focus to each other until the page froze. One copy (`radix-layer-singletons` guard) and
 * this journey keep both away. A frozen page fails here by timing out on its next assertion.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import type { Locator, Page } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { dictationEnabled } from '../fixtures/selection-assist';

const en = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/en/translation.json'), 'utf8')
) as {
  common: { edit: string };
  selectionAssist: { label: string; voice: { dictate: string } };
  settings: {
    mcp: {
      edit_title: string;
      field_auth_type: string;
      auth_none: string;
      auth_api_key: string;
      auth_bearer: string;
      auth_oauth2: string;
    };
  };
};
const mcp = en.settings.mcp;

test.use({
  launchOptions: {
    args: [
      '--disable-features=AutofillServerCommunication',
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
    ],
  },
});

const SERVER_ID = '64ecab78-0000-4000-8000-0000000000aa';
const stamp = '2026-11-13T16:45:30Z';
// Like the production row of the incident: switched to OAuth by an edit, then failed its test.
const server = {
  id: SERVER_ID,
  name: 'Studio',
  url: 'https://mcp.studio.example/mcp',
  plugin_id: null,
  auth_type: 'oauth2',
  status: 'error',
  is_enabled: true,
  domain_description: null,
  timeout_seconds: 120,
  hitl_required: null,
  iterative_mode: false,
  react_expand_iterative: null,
  suspended_tool_choices: 0,
  header_name: null,
  has_credentials: false,
  has_oauth_credentials: false,
  oauth_scopes: null,
  tool_count: 0,
  tools: [],
  last_connected_at: null,
  last_error: 'Server returned an error response',
  created_at: stamp,
  updated_at: stamp,
};

function routes(dictation: boolean): MockRoute[] {
  const capabilities = dictation
    ? dictationEnabled.json.capabilities
    : { tool_assists: { enabled: true, family: 'work' } };
  return [
    {
      url: '**/api/v1/config',
      json: { ...appConfig, features: { ...appConfig.features, mcp_enabled: true }, capabilities },
    },
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    { url: '**/api/v1/mcp/servers/known', json: { servers: [] } },
    {
      url: `**/api/v1/mcp/servers/${SERVER_ID}/behavior`,
      json: {
        confirmation: { always: true, source: 'instance' },
        pipeline: { driver: 'direct', before_task: false, per_call: 'card_after_task' },
        react: { driver: 'direct', before_task: false, per_call: 'in_loop' },
        tools: [],
        unattended_refused: [],
        notes: [],
      },
    },
    {
      url: '**/api/v1/mcp/servers',
      method: 'GET',
      json: {
        servers: [server],
        total: 1,
        defaults: {
          confirmation_instance: true,
          confirmation_account: null,
          confirmation_effective: true,
          react_direct_tools_default: true,
          dedicated_agents_available: true,
        },
      },
    },
  ];
}

async function openEditForm(page: Page): Promise<{ trigger: Locator; url: Locator }> {
  await page.goto('/en/dashboard/settings?section=mcp-servers');
  await waitForHydration(page, 'main');
  await page.getByRole('button', { name: en.common.edit, exact: true }).click();
  const dialog = page.getByRole('dialog', { name: mcp.edit_title });
  await expect(dialog).toBeVisible();
  return {
    trigger: dialog.getByRole('combobox', { name: mcp.field_auth_type }),
    url: dialog.locator('input[id$="-mcp-url"]'),
  };
}

/** The keyboard path: the open list holds the focus, the arrows move in it, Enter chooses. */
async function chooseBearerByKeyboard(page: Page, trigger: Locator): Promise<void> {
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('listbox')).toBeVisible();
  await expect(page.getByRole('option', { name: mcp.auth_oauth2, exact: true })).toBeFocused();
  // Radix moves the focus of an arrow key on the next tick: wait for it, as a hand would.
  await page.keyboard.press('ArrowUp');
  await expect(page.getByRole('option', { name: mcp.auth_bearer, exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(trigger).toHaveText(mcp.auth_bearer);
  await expect(trigger).toBeFocused();
}

test('a list inside a dialog takes the keyboard', async ({ page, authenticate, mockApi }) => {
  await authenticate();
  await mockApi(routes(false));
  const { trigger } = await openEditForm(page);
  await chooseBearerByKeyboard(page, trigger);
});

test('the dictation bubble beside a dialog field never freezes its list', async ({
  page,
  context,
  authenticate,
  mockApi,
  browserName,
}) => {
  test.skip(browserName !== 'chromium', 'Chromium alone supplies a fake microphone.');
  await context.grantPermissions(['microphone']);
  await authenticate();
  await mockApi(routes(true));
  const { trigger, url } = await openEditForm(page);

  await url.click();
  await expect(page.getByRole('toolbar', { name: en.selectionAssist.voice.dictate })).toBeVisible();
  await trigger.click();
  await page.getByRole('option', { name: mcp.auth_none, exact: true }).click();
  await expect(trigger).toHaveText(mcp.auth_none);

  // And from the keyboard, with the bubble back on the field.
  await url.click();
  await expect(page.getByRole('toolbar', { name: en.selectionAssist.voice.dictate })).toBeVisible();
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('option', { name: mcp.auth_none, exact: true })).toBeFocused();
  // Radix moves the focus of an arrow key on the next tick: wait for it, as a hand would.
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('option', { name: mcp.auth_api_key, exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(trigger).toHaveText(mcp.auth_api_key);
});

test('the selection bubble beside a dialog field never freezes its list', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await mockApi(routes(false));
  const { trigger, url } = await openEditForm(page);

  await url.click();
  await url.selectText();
  await expect(page.getByRole('toolbar', { name: en.selectionAssist.label })).toBeVisible();
  await trigger.click();
  await page.getByRole('option', { name: mcp.auth_none, exact: true }).click();
  await expect(trigger).toHaveText(mcp.auth_none);
});

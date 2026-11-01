/**
 * Who decides when LIA asks before an MCP tool, and what a server will do
 * (spec 2026-10-30 § 1-4 and 6), against the hermetic API.
 *
 * The page holds no rule: what it offers and shows is what the API publishes, and a
 * change that makes LIA ask less is listed — from the API's own `questions_lost` —
 * before it applies. Measured at a desktop and a phone width: no horizontal overflow,
 * no axe violation, the keyboard reaches every step, and the focus never falls to
 * <body> when an alert closes.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { test, expect } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import type { UserMCPServer } from '../../src/hooks/useUserMCPServers';
import type {
  MCPConfirmationReason,
  MCPConfirmationSource,
  MCPQuestionLoss,
  MCPServerBehavior,
  MCPToolChoice,
  UserMCPDefaults,
} from '../../src/lib/mcp-behavior';

const serverId = '11111111-1111-4111-8111-1111111111aa';
const stamp = '2026-10-30T10:00:00Z';
const server: UserMCPServer = {
  id: serverId,
  name: 'Notes',
  url: 'https://notes.example.test/mcp',
  plugin_id: null,
  auth_type: 'none',
  status: 'active',
  is_enabled: true,
  domain_description: 'Personal notes',
  timeout_seconds: 30,
  hitl_required: null,
  iterative_mode: false,
  react_expand_iterative: null,
  suspended_tool_choices: 0,
  header_name: null,
  has_credentials: false,
  has_oauth_credentials: false,
  oauth_scopes: null,
  tool_count: 2,
  tools: [],
  last_connected_at: stamp,
  last_error: null,
  created_at: stamp,
  updated_at: stamp,
};
const instanceAsks: UserMCPDefaults = {
  confirmation_instance: true,
  confirmation_account: null,
  confirmation_effective: true,
  react_direct_tools_default: true,
  dedicated_agents_available: true,
};
const losses: MCPQuestionLoss[] = [
  { server_id: serverId, server_name: 'Notes', tool_name: 'read_note' },
];

function behavior(
  source: MCPConfirmationSource,
  reason: MCPConfirmationReason,
  deleteChoice: MCPToolChoice | null = null
): MCPServerBehavior {
  return {
    confirmation: { always: true, source },
    pipeline: { driver: 'direct', before_task: false, per_call: 'card_after_task' },
    react: { driver: 'direct', before_task: false, per_call: 'in_loop' },
    tools: [
      {
        tool_name: 'delete_note',
        title: 'Delete a note',
        description: 'Deletes a note forever',
        asks: deleteChoice !== 'never',
        reason: deleteChoice === 'never' ? 'tool_never' : reason,
        choice: deleteChoice,
        suspended: false,
        default_asks: true,
      },
      {
        tool_name: 'read_note',
        title: null,
        description: 'Reads a note',
        asks: true,
        reason,
        choice: null,
        suspended: false,
        default_asks: true,
      },
    ],
    unattended_refused: ['delete_note', 'read_note'],
    notes: [],
  };
}

const mcpConfig = {
  url: '**/api/v1/config',
  json: { ...appConfig, features: { ...appConfig.features, mcp_enabled: true } },
};
const noBroadcast = { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } };

async function expectAccessible(page: Page, selector: string) {
  const { violations } = await new AxeBuilder({ page })
    .include(selector)
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(violations).toEqual([]);
}

/** A card's action: inline from `sm`, through the card's menu on a phone. */
async function cardAction(page: Page, width: number, label: string) {
  if (width < 640) {
    await page.getByRole('button', { name: 'Actions — Notes' }).click();
    await page.getByRole('menuitem', { name: label }).click();
  } else await page.getByRole('button', { name: label, exact: true }).click();
}

for (const width of [1280, 320]) {
  test(`the account strategy lists a loosening before it applies at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const user = await authenticate({ language: 'en' });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    let account: boolean | null = null;
    const previews: unknown[] = [];
    const patches: unknown[] = [];
    await mockApi([
      mcpConfig,
      noBroadcast,
      {
        url: '**/api/v1/mcp/servers',
        method: 'GET',
        handler: async route => {
          const defaults = {
            ...instanceAsks,
            confirmation_account: account,
            confirmation_effective: account ?? true,
          };
          await route.fulfill({ json: { servers: [server], total: 1, defaults } });
        },
      },
      {
        url: '**/api/v1/mcp/servers/strategy/preview',
        method: 'POST',
        handler: async route => {
          previews.push(route.request().postDataJSON());
          await route.fulfill({ json: { questions_lost: losses } });
        },
      },
      {
        url: `**/api/v1/users/${user.id}`,
        method: 'PATCH',
        handler: async route => {
          const body = route.request().postDataJSON() as { mcp_hitl_required: boolean | null };
          patches.push(body);
          account = body.mcp_hitl_required;
          await route.fulfill({ json: {} });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=mcp-servers');
    await awaitStyledPage(page, 'mcp confirmation strategy');

    const strategy = page.getByRole('group', { name: 'When LIA asks before using an MCP tool' });
    await expect(strategy.getByRole('radio', { name: 'Instance default' })).toBeChecked();
    await expect(
      strategy.getByText("Follows the instance's setting — currently: always ask.")
    ).toBeVisible();
    await expectNoOverflow(page, `strategy at ${width}px`);
    await expectAccessible(page, 'fieldset');

    // A loosening is listed first, and cancelling it changes nothing.
    await strategy.getByText('Follow the declarations', { exact: true }).click();
    const alert = page.getByRole('alertdialog', { name: 'LIA will ask less' });
    await expect(alert).toBeVisible();
    await expect(alert.getByText('read_note', { exact: true })).toBeVisible();
    // One row per tool, named with its server: whether LIA asks no longer depends on the mode.
    await expect(alert.getByRole('listitem')).toHaveText(['read_note — Notes']);
    expect(patches).toEqual([]);
    await expectNoOverflow(page, `loosening alert at ${width}px`);
    await expectAccessible(page, '[role="alertdialog"]');
    await alert.getByRole('button', { name: 'Cancel' }).click();
    await expect(alert).toBeHidden();
    const declarations = strategy.getByRole('radio', { name: 'Follow the declarations' });
    await expect(declarations).toBeFocused();
    await expect(strategy.getByRole('radio', { name: 'Instance default' })).toBeChecked();
    expect(patches).toEqual([]);

    // The keyboard reaches every step: choose, move to the confirmation, apply.
    await page.keyboard.press('Space');
    await expect(alert).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(alert.getByRole('button', { name: 'Apply the change' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect.poll(() => patches).toEqual([{ mcp_hitl_required: false }]);
    await expect(page.getByText('Confirmation strategy saved')).toBeVisible();
    await expect(declarations).toBeChecked();
    expect(previews).toEqual([{ mcp_hitl_required: false }, { mcp_hitl_required: false }]);
    expect(errors).toEqual([]);
  });

  test(`a server says what it will do and previews a change before saving at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'en' });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const previews: unknown[] = [];
    const updates: unknown[] = [];
    await mockApi([
      mcpConfig,
      noBroadcast,
      {
        url: '**/api/v1/mcp/servers',
        method: 'GET',
        json: { servers: [server], total: 1, defaults: instanceAsks },
      },
      {
        url: `**/api/v1/mcp/servers/${serverId}/behavior`,
        method: 'GET',
        json: behavior('instance', 'instance_always'),
      },
      {
        url: `**/api/v1/mcp/servers/${serverId}/behavior/preview`,
        method: 'POST',
        handler: async route => {
          const body = route.request().postDataJSON() as { hitl_required?: boolean | null };
          previews.push(body);
          const shown =
            body.hitl_required === true
              ? behavior('server', 'server_always')
              : behavior('instance', 'instance_always');
          await route.fulfill({ json: { behavior: shown, questions_lost: [] } });
        },
      },
      {
        url: `**/api/v1/mcp/servers/${serverId}`,
        method: 'PATCH',
        handler: async route => {
          updates.push(route.request().postDataJSON());
          await route.fulfill({ json: { ...server, hitl_required: true } });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=mcp-servers');
    await awaitStyledPage(page, 'mcp server behavior');

    // What it will do, from its card: tool by tool, why LIA asks.
    await cardAction(page, width, 'What it will do');
    const inspection = page.getByRole('dialog', { name: 'What Notes will do' });
    const synthesis = inspection.getByRole('region', { name: 'What this server will do' });
    await expect(synthesis.getByText('Delete a note', { exact: true })).toBeVisible();
    await expect(synthesis.getByText('Deletes a note forever')).toBeVisible();
    await expect(synthesis.getByText('Instance default: always ask.').first()).toBeVisible();
    await expectNoOverflow(page, `what it will do at ${width}px`);
    await expectAccessible(page, '[role="dialog"]');
    await page.keyboard.press('Escape');
    await expect(inspection).toBeHidden();

    // The form offers the server's own choices and follows them before saving.
    await cardAction(page, width, 'Edit');
    const form = page.getByRole('dialog', { name: 'Edit MCP Server' });
    const confirmation = form.getByRole('group', { name: 'When LIA asks before using its tools' });
    await expect(confirmation.getByRole('radio', { name: 'Like my strategy' })).toBeChecked();
    await expect(
      confirmation.getByText('Follows your strategy — currently: always ask.')
    ).toBeVisible();
    const driver = form.getByRole('group', { name: 'Who drives this server' });
    await expect(driver.getByRole('radio', { name: 'LIA uses its tools directly' })).toBeChecked();
    await expect(form.getByRole('switch')).toHaveCount(0);

    await confirmation.getByText('Always ask', { exact: true }).click();
    await expect(
      form
        .getByRole('region', { name: 'What this server will do' })
        .getByText('This server: always ask.')
        .first()
    ).toBeVisible();
    await expectNoOverflow(page, `server form at ${width}px`);
    await expectAccessible(page, '[role="dialog"]');

    // Asking more needs no alert: it is saved at once.
    await form.getByRole('button', { name: 'Save', exact: true }).click();
    await expect.poll(() => updates).toEqual([{ hitl_required: true }]);
    await expect(form).toBeHidden();
    await expect(page.getByText('MCP server updated')).toBeVisible();
    expect(previews.every(body => JSON.stringify(body) === '{"hitl_required":true}')).toBe(true);
    expect(errors).toEqual([]);
  });

  test(`a tool's own choice is listed first when LIA would ask less at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'en' });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    let stored: MCPToolChoice | null = null;
    const previews: unknown[] = [];
    const writes: unknown[] = [];
    await mockApi([
      mcpConfig,
      noBroadcast,
      {
        url: '**/api/v1/mcp/servers',
        method: 'GET',
        json: { servers: [server], total: 1, defaults: instanceAsks },
      },
      {
        url: `**/api/v1/mcp/servers/${serverId}/behavior`,
        method: 'GET',
        handler: async route =>
          route.fulfill({ json: behavior('instance', 'instance_always', stored) }),
      },
      {
        url: `**/api/v1/mcp/servers/${serverId}/behavior/preview`,
        method: 'POST',
        handler: async route => {
          previews.push(route.request().postDataJSON());
          await route.fulfill({
            json: {
              behavior: behavior('instance', 'instance_always', 'never'),
              questions_lost: [
                { server_id: serverId, server_name: 'Notes', tool_name: 'delete_note' },
              ] satisfies MCPQuestionLoss[],
            },
          });
        },
      },
      {
        url: `**/api/v1/mcp/servers/${serverId}/tool-confirmations`,
        method: 'PUT',
        handler: async route => {
          const body = route.request().postDataJSON() as { choice: MCPToolChoice | null };
          writes.push(body);
          stored = body.choice;
          await route.fulfill({ json: behavior('instance', 'instance_always', stored) });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=mcp-servers');
    await awaitStyledPage(page, 'mcp tool choice');

    await cardAction(page, width, 'What it will do');
    const dialog = page.getByRole('dialog', { name: 'What Notes will do' });
    const select = dialog.getByRole('combobox', { name: 'When LIA asks before Delete a note' });
    await expect(select).toHaveValue('default');
    await expect(select.getByRole('option', { name: 'By default (asks)' })).toBeAttached();
    await expectNoOverflow(page, `tool choices at ${width}px`);
    await expectAccessible(page, '[role="dialog"]');

    await select.selectOption('never');
    const alert = page.getByRole('alertdialog', { name: 'LIA will ask less' });
    await expect(alert.getByRole('listitem')).toHaveText(['delete_note — Notes']);
    expect(writes).toEqual([]);
    await alert.getByRole('button', { name: 'Apply the change' }).click();

    await expect.poll(() => writes).toEqual([{ tool_name: 'delete_note', choice: 'never' }]);
    await expect(select).toHaveValue('never');
    await expect(
      dialog.getByText('Your choice for this tool: never ask.', { exact: true })
    ).toBeVisible();
    expect(previews).toEqual([{ tool_choices: { delete_note: 'never' } }]);
    expect(errors).toEqual([]);
  });
}

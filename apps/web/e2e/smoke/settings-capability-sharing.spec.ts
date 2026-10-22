/** Native settings controls -> closed transfer API -> recipient-owned disabled copy. */
import { test, expect } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import type { Skill } from '../../src/hooks/useSkills';
import type { InstalledPlugin } from '../../src/hooks/usePlugins';
import type { UserMCPServer } from '../../src/hooks/useUserMCPServers';
import AxeBuilder from '@axe-core/playwright';

const sourceId = '11111111-1111-4111-8111-111111111111';
const transferId = '22222222-2222-4222-8222-222222222222';
const connectionId = '33333333-3333-4333-8333-333333333333';
const stamp = '2026-10-18T12:00:00Z';
const name = 'example-capability';
const origin = {
  sender_display_name: 'Camille Example',
  shared_at: stamp,
  transfer_id: transferId,
};
const skill: Skill = {
  skill_id: sourceId,
  name,
  description: 'Useful personal instructions',
  descriptions: null,
  scope: 'user',
  category: null,
  priority: 0,
  always_loaded: false,
  has_scripts: false,
  has_plan_template: false,
  enabled_for_user: false,
  provenance: 'peer',
  is_third_party: false,
  shared_origin: origin,
};
const plugin: InstalledPlugin = {
  id: sourceId,
  name,
  description: 'A personal plugin',
  version: '1.0.0',
  spec_version: '1.0.0',
  skill_names: [],
  server_names: [],
  created_at: stamp,
  updated_at: stamp,
  shared_origin: origin,
};
const server: UserMCPServer = {
  id: sourceId,
  name,
  url: 'https://mcp.example.test/api',
  plugin_id: null,
  auth_type: 'bearer',
  status: 'auth_required',
  is_enabled: false,
  domain_description: 'A personal connector',
  timeout_seconds: 30,
  hitl_required: null,
  iterative_mode: false,
  header_name: null,
  has_credentials: false,
  has_oauth_credentials: false,
  oauth_scopes: null,
  tool_count: 0,
  tools: [],
  last_connected_at: null,
  last_error: null,
  created_at: stamp,
  updated_at: stamp,
  shared_origin: origin,
};

for (const kind of ['skill', 'plugin', 'mcp'] as const) {
  for (const width of [1280, 320]) {
    test(`shares ${kind} with explicit confirmation and renders its origin at ${width}px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await authenticate({ language: 'en' });
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      const requests: unknown[] = [];
      const preview = {
        id: transferId,
        kind,
        name,
        status: 'preparing',
        digest: 'a'.repeat(64),
        files: [{ path: 'SKILL.md', size: 100 }],
        omitted: ['.env'],
        requires_credentials: kind !== 'skill',
        created_at: stamp,
        transferred_at: null,
        components: [],
        error_code: null,
      };
      await mockApi([
        {
          url: '**/api/v1/config',
          json: {
            ...appConfig,
            features: {
              ...appConfig.features,
              peers_enabled: true,
              skills_enabled: true,
              mcp_enabled: true,
              plugins_enabled: true,
            },
          },
        },
        { url: '**/api/v1/skills', json: { skills: [skill], total: 1 } },
        { url: '**/api/v1/plugins', json: { plugins: [plugin], total: 1 } },
        { url: '**/api/v1/mcp/servers', json: { servers: [server], total: 1 } },
        {
          url: '**/api/v1/peers/connections',
          json: [{ id: connectionId, status: 'accepted', peer_display_name: 'Alice Example' }],
        },
        { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
        {
          url: '**/api/v1/peers/capability-transfers/preview',
          method: 'POST',
          handler: async route => {
            requests.push(route.request().postDataJSON());
            await route.fulfill({ json: preview });
          },
        },
        {
          url: `**/api/v1/peers/capability-transfers/${transferId}/send`,
          method: 'POST',
          handler: async route => {
            requests.push(route.request().postDataJSON());
            await route.fulfill({
              json: { ...preview, status: 'installed', transferred_at: stamp },
            });
          },
        },
      ]);
      const section = { skill: 'skills', plugin: 'plugins', mcp: 'mcp-servers' }[kind];
      await page.goto(`/en/dashboard/settings?section=${section}`);
      await awaitStyledPage(page, `${kind} sharing`);
      if (kind === 'skill')
        await page.locator('summary').filter({ hasText: 'My imported skills' }).click();
      await expect(page.getByRole('note', { name: /Shared by Camille Example/ })).toBeVisible();
      if (kind === 'mcp')
        await expect(page.getByRole('switch').filter({ visible: true }).last()).not.toBeChecked();
      if (width < 640) {
        await page.getByRole('button', { name: `Actions — ${name}` }).click();
        await page.getByRole('menuitem', { name: `Share ${name}` }).click();
      } else await page.getByRole('button', { name: `Share ${name}`, exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Share a capability' });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole('button', { name: 'Preview', exact: true })).toBeDisabled();
      expect(requests).toEqual([]);
      await dialog.getByRole('radio', { name: 'Alice Example' }).check();
      await dialog.getByRole('button', { name: 'Preview', exact: true }).click();
      await expect(dialog.getByText('SKILL.md', { exact: true })).toBeVisible();
      await expect(dialog.getByText('.env', { exact: true })).toBeVisible();
      expect(requests[0]).toMatchObject({ connection_id: connectionId, kind, source_id: sourceId });
      await expectNoOverflow(page, `${kind} confirmation at ${width}px`);
      const accessibility = await new AxeBuilder({ page })
        .include('[role="dialog"]')
        .withTags(['wcag2a', 'wcag2aa'])
        .analyze();
      expect(accessibility.violations).toEqual([]);
      await dialog.getByRole('button', { name: 'Send and install', exact: true }).click();
      // A complete installation closes the dialog and is announced instead:
      // what was shared, with whom, and the state it has on the other side.
      const shared = { skill: 'Skill', plugin: 'Plugin', mcp: 'MCP server' }[kind];
      await expect(
        page.getByText(`${shared} “${name}” shared with Alice Example`, { exact: true })
      ).toBeVisible();
      await expect(
        page.getByText('Installed for the recipient, initially disabled', { exact: true })
      ).toBeVisible();
      expect(requests[1]).toEqual({ expected_digest: 'a'.repeat(64) });
      await expect(dialog).toHaveCount(0);
      expect(errors).toEqual([]);
    });
  }
}

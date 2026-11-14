/**
 * MCP servers — a known server is added from the gallery, without typing its address.
 *
 * Hermetic, in a real engine, at a desktop and a phone width. The API publishes
 * the known servers; « Known MCPs » opens a gallery of tiles of one size, each
 * with the vendor's icon (a file this application serves), the server's name,
 * how one signs in and what it is for. A server the person already has is
 * greyed and badged « Installed ». A tile opens the create form already filled;
 * the person types only their own key, and what is saved is exactly what was
 * shown. Once the form closes, the focus is back on « Known MCPs ».
 */
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { test, expect } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const english = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/en/translation.json'), 'utf8')
) as {
  common: { save: string };
  settings: {
    mcp: {
      add_title: string;
      field_name: string;
      field_url: string;
      field_api_key: string;
      known: {
        button: string;
        title: string;
        installed: string;
        installed_hint: string;
        scheme: Record<string, string>;
        next: Record<string, string>;
        servers: Record<string, string>;
      };
    };
  };
};
const copy = english.settings.mcp;

const CALA = {
  key: 'cala',
  name: 'Cala',
  url: 'https://api.cala.ai/mcp/',
  auth_type: 'api_key',
  domain_description: 'Cala: verified knowledge with its sources.',
  icon: 'cala.png',
  header_name: 'X-API-Key',
};
const CONTEXT7 = {
  key: 'context7',
  name: 'Context7',
  url: 'https://mcp.context7.com/mcp',
  auth_type: 'none',
  domain_description: 'Up-to-date documentation of software libraries.',
  icon: 'context7.png',
};
const GITHUB = {
  key: 'github',
  name: 'GitHub',
  url: 'https://api.githubcopilot.com/mcp/',
  auth_type: 'oauth2',
  domain_description: "The person's GitHub.",
  icon: 'github.svg',
  oauth_scopes: 'repo',
  own_oauth_client: true,
};
const NOTION = {
  key: 'notion',
  name: 'Notion',
  url: 'https://mcp.notion.com/mcp',
  auth_type: 'oauth2',
  domain_description: "The person's Notion workspace: pages, databases and comments.",
  icon: 'notion.png',
};
const stamp = '2026-11-13T16:45:30Z';
// Context7, already added by the person: its address typed with a trailing slash.
const INSTALLED = {
  id: '64ecab78-0000-4000-8000-0000000000c7',
  name: 'Docs',
  url: 'https://mcp.context7.com/mcp/',
  plugin_id: null,
  auth_type: 'none',
  status: 'active',
  is_enabled: true,
  domain_description: null,
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
const defaults = {
  confirmation_instance: true,
  confirmation_account: null,
  confirmation_effective: true,
  react_direct_tools_default: true,
  dedicated_agents_available: true,
};

for (const width of [1280, 360]) {
  test(`a known server is added from the gallery and saved as shown at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'en' });
    const created: Record<string, unknown>[] = [];
    await mockApi([
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, mcp_enabled: true } },
      },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      {
        url: '**/api/v1/mcp/servers/known',
        json: {
          servers: [CALA, CONTEXT7, GITHUB, NOTION],
          oauth_redirect_uri: 'https://lia.example/api/v1/mcp/servers/oauth/callback',
        },
      },
      {
        url: '**/api/v1/mcp/servers/*/behavior',
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
        json: { servers: [INSTALLED], total: 1, defaults },
      },
      {
        url: '**/api/v1/mcp/servers',
        method: 'POST',
        handler: async route => {
          created.push(route.request().postDataJSON() as Record<string, unknown>);
          // The row the API answers is appended to the list: a whole server.
          await route.fulfill({
            status: 201,
            json: {
              ...INSTALLED,
              id: '64ecab78-0000-4000-8000-0000000000ca',
              name: 'Cala',
              url: CALA.url,
              auth_type: 'api_key',
              header_name: 'X-API-Key',
              has_credentials: true,
              tool_count: 0,
              last_connected_at: null,
            },
          });
        },
      },
    ]);

    await page.goto('/en/dashboard/settings?section=mcp-servers');
    await awaitStyledPage(page, 'mcp known servers');
    const knownButton = page.getByRole('button', { name: copy.known.button });
    await knownButton.click();

    const gallery = page.getByRole('dialog', { name: copy.known.title });
    await expect(gallery).toBeVisible();
    const tiles = gallery.getByRole('listitem').getByRole('button');
    await expect(tiles).toHaveCount(4);

    // Every tile is the same size, whatever its name or its description.
    const boxes = await tiles.evaluateAll(nodes =>
      nodes.map(node => {
        const box = node.getBoundingClientRect();
        return { width: Math.round(box.width), height: Math.round(box.height) };
      })
    );
    expect(new Set(boxes.map(box => `${box.width}x${box.height}`)).size).toBe(1);

    // The vendor's icons are this application's files, and they are drawn.
    const icons = gallery.locator('img');
    await expect(icons).toHaveCount(4);
    await expect
      .poll(() =>
        icons.evaluateAll(nodes =>
          nodes.every(node => node instanceof HTMLImageElement && node.naturalWidth > 0)
        )
      )
      .toBe(true);
    expect(await icons.evaluateAll(nodes => nodes.map(node => node.getAttribute('src')))).toEqual([
      '/mcp-icons/cala.png',
      '/mcp-icons/context7.png',
      '/mcp-icons/github.svg',
      '/mcp-icons/notion.png',
    ]);

    // Context7 is already the person's: greyed, badged, said, never picked again.
    const context7 = gallery.getByRole('button', { name: 'Context7' });
    await expect(context7).toHaveAttribute('aria-disabled', 'true');
    await expect(context7.getByText(copy.known.installed)).toBeVisible();
    await expect(context7).toHaveAccessibleDescription(new RegExp(`^${copy.known.installed_hint}`));
    // `aria-disabled` keeps it in the tab order, where the keyboard can still press it:
    // the press opens nothing (a pointer cannot reach it, Playwright refuses that click).
    await context7.focus();
    await page.keyboard.press('Enter');
    await expect(gallery).toBeVisible();
    await expect(page.getByRole('dialog', { name: copy.add_title })).toHaveCount(0);

    const cala = gallery.getByRole('button', { name: 'Cala' });
    await expect(cala).toHaveAccessibleDescription(
      `${copy.known.scheme.api_key} ${copy.known.servers.cala}`
    );
    await expectNoOverflow(page, `Known MCP gallery at ${width}px`);
    expect(
      (
        await new AxeBuilder({ page })
          .include('[role="dialog"]')
          .withTags(['wcag2a', 'wcag2aa'])
          .analyze()
      ).violations
    ).toEqual([]);

    // A tile opens the create form already filled; only the person's key is typed.
    await cala.click();
    const form = page.getByRole('dialog', { name: copy.add_title });
    await expect(form).toBeVisible();
    await expect(gallery).toBeHidden();
    await expect(form.getByRole('textbox', { name: copy.field_name, exact: true })).toHaveValue(
      'Cala'
    );
    await expect(form.getByRole('textbox', { name: copy.field_url, exact: true })).toHaveValue(
      CALA.url
    );
    await expect(form.getByText(copy.known.servers.cala)).toBeVisible();
    await expect(
      form.getByText(copy.known.next.api_key.replaceAll('{{name}}', 'Cala'))
    ).toBeVisible();
    await expectNoOverflow(page, `Known MCP form at ${width}px`);

    await form.getByLabel(copy.field_api_key, { exact: true }).fill('typed-by-the-person');
    await form.getByRole('button', { name: english.common.save }).click();

    await expect.poll(() => created.length).toBe(1);
    expect(created[0]).toMatchObject({
      name: 'Cala',
      url: CALA.url,
      auth_type: 'api_key',
      api_key: 'typed-by-the-person',
      header_name: 'X-API-Key',
      domain_description: CALA.domain_description,
    });
    // The form is gone with its tile: the focus is back where the gallery was opened.
    await expect(form).toBeHidden();
    await expect(knownButton).toBeFocused();
  });
}

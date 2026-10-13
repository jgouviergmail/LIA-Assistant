import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes, expectSessionCookie, waitForHydration } from '../fixtures';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const server = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const conversation = '00000000-0000-4000-8000-00000000c001';
const secret = 'controlled_private_api_key';
const refs = [{ command_id: command }];

for (const { width, lost } of [{ width: 1280, lost: false }, { width: 320, lost: false }, { width: 320, lost: true }]) {
  test(`private MCP form follows HITL at ${width}px, lost ${lost}`, async ({ page, authenticate, mockApi, baseURL, browserName }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    if (!baseURL) throw new Error('An HTTP proof server is required');
    await page.context().addCookies([{ name: 'lia_session', value: 'mcp-private-e2e-session', url: baseURL, httpOnly: true, sameSite: 'Lax' }]);
    await mockApi(chatRoutes([]));
    let confirmed = false;
    let attempts = 0;
    const expires = new Date(Date.now() + 300_000).toISOString();
    function observed() {
      const interaction = attempts ? null : { interaction_id: command, kind: 'device', expires_at: expires };
      const phase = attempts ? 'committed' : 'waiting';
      return { schema_version: 1, command_id: command, operation_id: 'personal_mcp.configuration', phase,
        expires_at: expires, interaction, outcome: { success: !!attempts, phase, committed: !!attempts,
          no_op: false, error_code: null, interaction, values: { personal_mcp_configuration: attempts
            ? { server_id: server, configuration_saved: true, connection_verified: false }
            : { server_id: null, creating: true, requires_private_browser_form: true } } } };
    }
    await mockApi([
      { url: '**/api/v1/agents/hitl/pending', handler: async route => {
        await route.fulfill({ json: confirmed ? null : {
          message_id: 'mcp-configuration-hitl', interrupt_ts: new Date().toISOString(),
          generated_question: 'Confirm opening a private configuration form for a personal MCP server?',
          action_requests: [{ type: 'draft_critique', draft_type: 'application_action', draft_id: 'mcp-private-e2e',
            available_actions: [{ action: 'confirm', label: 'confirm', style: 'primary' }, { action: 'cancel', label: 'cancel', style: 'destructive' }], registry_ids: [] }],
        } });
      } },
      { url: '**/api/v1/agents/chat/stream', method: 'POST', handler: async route => {
        expect(route.request().postDataJSON().hitl_decision?.action).toBe('confirm');
        confirmed = true;
        await route.fulfill({ contentType: 'text/event-stream', body:
          'data: {"type":"token","content":"Complete the private MCP form in this browser.","metadata":null}\n\n' +
          `data: ${JSON.stringify({ type: 'done', content: '', metadata: { application_interactions: refs } })}\n\n` });
      } },
      { url: '**/api/v1/conversations/me/messages*', handler: async route => {
        await route.fulfill({ json: { messages: confirmed ? [{ id: '00000000-0000-4000-8000-000000001001',
          role: 'assistant', content: 'Complete the private MCP form in this browser.', created_at: new Date().toISOString(),
          message_metadata: { application_interactions: refs } }] : [], conversation_id: conversation,
          total_count: confirmed ? 1 : 0, has_more: false, next_cursor: null } });
      } },
      { url: `**/api/v1/application-commands/${command}`, handler: async route => {
        expect(confirmed).toBe(true); await route.fulfill({ json: observed() });
      } },
      { url: `**/api/v1/application-commands/${command}/personal-mcp`, method: 'POST', handler: async route => {
        expect(confirmed).toBe(true);
        expect(route.request().postDataJSON()).toEqual({ values: { name: 'Controlled server', url: 'https://example.org/mcp',
          auth_type: 'api_key', api_key: secret, header_name: 'X-API-Key', timeout_seconds: 30, iterative_mode: false } });
        await expectSessionCookie(route.request(), browserName, 'lia_session=mcp-private-e2e-session');
        attempts += 1;
        if (lost) await route.abort('connectionreset');
        else await route.fulfill({ headers: { 'Cache-Control': 'no-store' }, json: observed() });
      } },
    ]);
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'section[aria-label="Draft to review"] button');
    expect(attempts).toBe(0);
    await page.getByRole('region', { name: 'Draft to review' }).getByRole('button', { name: 'Confirm', exact: true }).click();
    const card = page.getByRole('region', { name: 'Configure a personal MCP server' });
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: 'Open the private form' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('textbox', { name: 'Name', exact: true }).fill('Controlled server');
    await dialog.getByRole('textbox', { name: 'Server URL', exact: true }).fill('https://example.org/mcp');
    await dialog.getByRole('combobox', { name: 'Authentication type' }).click();
    await page.getByRole('option', { name: 'API Key', exact: true }).click();
    await dialog.getByLabel('API Key', { exact: true }).fill(secret);
    expect(attempts).toBe(0);
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await dialog.getByRole('button', { name: 'Save', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(dialog).toHaveCount(0);
    if (lost) await expect(card.getByRole('status')).toContainText('The result is not yet confirmed');
    else await expect(card.getByRole('status')).toContainText('Configuration saved. The connection has not been tested.');
    expect(attempts).toBe(1);
    await expect(card.getByRole('button', { name: 'Check result' })).toBeFocused();
    await page.reload();
    await waitForHydration(page, 'section[aria-label="Configure a personal MCP server"] button');
    await expect(page.locator(`input[value="${secret}"]`)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Open the private form' })).toHaveCount(0);
    expect(attempts).toBe(1);
  });
}

import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes, waitForHydration } from '../fixtures';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const server = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const refs = [{ command_id: command }];

for (const { width, lost } of [{ width: 1280, lost: false }, { width: 320, lost: false }, { width: 320, lost: true }]) {
  test(`OAuth follows HITL and provider return at ${width}px, lost ${lost}`, async ({ page, authenticate, mockApi, baseURL }) => {
    if (!baseURL) throw new Error('An HTTP proof server is required');
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    await page.context().addCookies([{ name: 'lia_session', value: 'mcp-oauth-e2e', url: baseURL, httpOnly: true, sameSite: 'Lax' }]);
    await mockApi(chatRoutes([]));
    let confirmed = false, started = false, staged = false, attempts = 0;
    const expires = new Date(Date.now() + 300_000).toISOString();
    const interaction = { interaction_id: command, kind: 'device', expires_at: expires };
    const waiting = { success: false, phase: 'waiting', committed: false, no_op: false, error_code: null, interaction,
      values: { personal_mcp_oauth: { id: server, requires_provider_authorization: true, requires_original_browser_completion: true } } };
    function observed() {
      const phase = attempts ? 'committed' : started ? 'resuming' : 'waiting';
      return { schema_version: 1, command_id: command, operation_id: 'personal_mcp.oauth_authorize', phase,
        expires_at: expires, interaction: started ? null : interaction,
        outcome: attempts ? { success: true, phase, committed: true, no_op: false, error_code: null, interaction: null,
          values: { personal_mcp_oauth: { server_id: server, authorization_saved: true, connection_verified: false } } }
          : started ? null : waiting, ...(started && !attempts ? { prior_outcome: waiting } : {}) };
    }
    await mockApi([
      { url: '**/api/v1/agents/hitl/pending', handler: async route => {
        await route.fulfill({ json: confirmed ? null : { message_id: 'oauth-hitl', interrupt_ts: new Date().toISOString(),
          generated_question: 'Confirm authorizing this personal MCP server?',
          action_requests: [{ type: 'draft_critique', draft_type: 'application_action', draft_id: 'oauth-draft',
            available_actions: [{ action: 'confirm', label: 'confirm', style: 'primary' }, { action: 'cancel', label: 'cancel', style: 'destructive' }], registry_ids: [] }] } });
      } },
      { url: '**/api/v1/agents/chat/stream', method: 'POST', handler: async route => {
        expect(route.request().postDataJSON().hitl_decision?.action).toBe('confirm'); confirmed = true;
        await route.fulfill({ contentType: 'text/event-stream', body: 'data: {"type":"token","content":"Complete provider authorization in your browser.","metadata":null}\n\n' +
          `data: ${JSON.stringify({ type: 'done', content: '', metadata: { application_interactions: refs } })}\n\n` });
      } },
      { url: '**/api/v1/conversations/me/messages*', handler: async route => {
        await route.fulfill({ json: { messages: confirmed ? [{ id: '00000000-0000-4000-8000-000000001001', role: 'assistant',
          content: 'Complete provider authorization in your browser.', created_at: new Date().toISOString(), message_metadata: { application_interactions: refs } }] : [],
          conversation_id: '00000000-0000-4000-8000-00000000c001', total_count: confirmed ? 1 : 0, has_more: false, next_cursor: null } });
      } },
      { url: `**/api/v1/application-commands/${command}`, handler: async route => {
        expect(confirmed).toBe(true); await route.fulfill({ json: observed() });
      } },
      { url: `**/api/v1/application-commands/${command}/personal-mcp-oauth/start`, method: 'POST', handler: async route => {
        expect(confirmed).toBe(true); expect(started).toBe(false); started = true;
        expect((await route.request().allHeaders()).cookie).toContain('lia_session=mcp-oauth-e2e');
        await route.fulfill({ headers: { 'Cache-Control': 'no-store' }, json: {
          command_id: command, authorization_url: `${baseURL}/controlled-provider?state=private-state` } });
      } },
      { url: '**/api/v1/mcp/servers/oauth/callback*', handler: async route => {
        expect(started).toBe(true); expect(attempts).toBe(0); staged = true;
        await route.fulfill({ status: 302, headers: { Location: `${baseURL}/en/dashboard/chat?mcp_oauth=pending&application_command_id=${command}` }, body: '' });
      } },
      { url: `**/api/v1/application-commands/${command}/personal-mcp-oauth/complete`, method: 'POST', handler: async route => {
        expect(staged).toBe(true); expect(attempts).toBe(0); attempts += 1;
        expect((await route.request().allHeaders()).cookie).toContain('lia_session=mcp-oauth-e2e');
        if (lost) await route.abort('connectionreset');
        else await route.fulfill({ json: observed() });
      } },
    ]);
    await page.route('**/controlled-provider*', async route => {
      expect(attempts).toBe(0);
      await route.fulfill({ contentType: 'text/html', body: `<html lang="en"><title>Controlled provider</title><body><a href="${baseURL}/api/v1/mcp/servers/oauth/callback?code=controlled-code&state=private-state">Authorize</a></body></html>` });
    });
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'section[aria-label="Draft to review"] button');
    expect(started).toBe(false); expect(attempts).toBe(0);
    await page.getByRole('region', { name: 'Draft to review' }).getByRole('button', { name: 'Confirm', exact: true }).click();
    let card = page.getByRole('region', { name: 'Authorize a personal MCP server' });
    await expect(card).toBeVisible();
    expect(started).toBe(false);
    await card.getByRole('button', { name: 'Open provider authorization' }).click();
    await page.getByRole('link', { name: 'Authorize', exact: true }).click();
    await waitForHydration(page, 'section[aria-label="Authorize a personal MCP server"] button');
    card = page.getByRole('region', { name: 'Authorize a personal MCP server' });
    expect(attempts).toBe(0);
    expect((await new AxeBuilder({ page }).include('section[aria-label="Authorize a personal MCP server"]').analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await card.getByRole('button', { name: 'Complete authorization' }).focus();
    await page.keyboard.press('Enter');
    await expect(card.getByRole('status')).toContainText(lost ? 'The result is not yet confirmed' : 'Authorization saved');
    expect(attempts).toBe(1);
    if (!lost) await expect(card.getByRole('button', { name: 'Check result' })).toBeFocused();
    await card.getByRole('button', { name: 'Check result' }).click();
    await expect(card.getByRole('status')).toContainText('Authorization saved');
    expect(attempts).toBe(1);
    await page.reload();
    await waitForHydration(page, 'section[aria-label="Authorize a personal MCP server"] button');
    await expect(page.getByRole('button', { name: 'Complete authorization' })).toHaveCount(0);
    expect(attempts).toBe(1);
    expect(await page.locator('body').innerText()).not.toContain('private-state');
  });
}

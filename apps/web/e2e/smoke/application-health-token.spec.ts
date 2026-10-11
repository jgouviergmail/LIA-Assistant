import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes, waitForHydration } from '../fixtures';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const conversation = '00000000-0000-4000-8000-00000000c001';
const secret = 'hm_controlled_browser_secret';
const refs = [{ command_id: command }];

for (const { width, lost } of [
  { width: 1280, lost: false },
  { width: 320, lost: false },
  { width: 320, lost: true },
]) {
  test(`confirmed health token is private and single-use at ${width}px, lost ${lost}`, async ({
    page,
    authenticate,
    mockApi,
    baseURL,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    if (!baseURL) throw new Error('An HTTP proof server is required');
    await page
      .context()
      .addCookies([
        {
          name: 'lia_session',
          value: 'health-e2e-session',
          url: baseURL,
          httpOnly: true,
          sameSite: 'Lax',
        },
      ]);
    await mockApi(chatRoutes([]));
    let confirmed = false;
    let attempts = 0;
    const expires = new Date(Date.now() + 300000).toISOString();
    await mockApi([
      {
        url: '**/api/v1/agents/hitl/pending',
        handler: async route => {
          await route.fulfill({
            json: confirmed
              ? null
              : {
                  message_id: 'health-token-hitl',
                  interrupt_ts: new Date().toISOString(),
                  generated_question: 'Confirmer la création d’un jeton santé dans ce navigateur ?',
                  action_requests: [
                    {
                      type: 'draft_critique',
                      draft_type: 'application_action',
                      draft_id: 'health-token-e2e',
                      available_actions: [
                        { action: 'confirm', label: 'confirm', style: 'primary' },
                        { action: 'cancel', label: 'cancel', style: 'destructive' },
                      ],
                      registry_ids: [],
                    },
                  ],
                },
          });
        },
      },
      {
        url: '**/api/v1/agents/chat/stream',
        method: 'POST',
        handler: async route => {
          const body: { hitl_decision?: { action?: string } } = route.request().postDataJSON();
          expect(body.hitl_decision?.action).toBe('confirm');
          confirmed = true;
          await route.fulfill({
            contentType: 'text/event-stream',
            body:
              'data: {"type":"token","content":"Votre navigateur peut maintenant créer le jeton santé.","metadata":null}\n\n' +
              `data: ${JSON.stringify({ type: 'done', content: '', metadata: { application_interactions: refs } })}\n\n`,
          });
        },
      },
      {
        url: '**/api/v1/conversations/me/messages*',
        handler: async route => {
          await route.fulfill({
            json: {
              messages: confirmed
                ? [
                    {
                      id: '00000000-0000-4000-8000-000000001001',
                      role: 'assistant',
                      content: 'Votre navigateur peut maintenant créer le jeton santé.',
                      created_at: new Date().toISOString(),
                      message_metadata: { application_interactions: refs },
                    },
                  ]
                : [],
              conversation_id: conversation,
              total_count: confirmed ? 1 : 0,
              has_more: false,
              next_cursor: null,
            },
          });
        },
      },
      {
        url: `**/api/v1/application-commands/${command}`,
        handler: async route => {
          const interaction = { interaction_id: command, kind: 'device', expires_at: expires };
          const phase = attempts ? 'committed' : 'waiting';
          await route.fulfill({
            json: {
              schema_version: 1,
              command_id: command,
              operation_id: 'health_token.create',
              phase,
              expires_at: expires,
              interaction: attempts ? null : interaction,
              outcome: {
                success: !!attempts,
                committed: !!attempts,
                phase,
                no_op: false,
                values: attempts
                  ? {
                      health_token_created: {
                        id: command,
                        token_prefix: 'hm_public',
                        label: 'Watch',
                      },
                    }
                  : {},
                error_code: null,
                interaction: attempts ? null : interaction,
              },
            },
          });
        },
      },
      {
        url: `**/api/v1/application-commands/${command}/health-token`,
        method: 'POST',
        handler: async route => {
          expect(confirmed).toBe(true);
          expect(route.request().postDataJSON()).toEqual({});
          expect((await route.request().allHeaders()).cookie).toContain(
            'lia_session=health-e2e-session'
          );
          attempts += 1;
          if (lost) await route.abort('connectionreset');
          else
            await route.fulfill({
              headers: { 'Cache-Control': 'no-store' },
              json: {
                id: command,
                token: secret,
                token_prefix: 'hm_public',
                label: 'Watch',
                created_at: new Date().toISOString(),
              },
            });
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page, 'section[aria-label="Brouillon à valider"] button');
    expect(attempts).toBe(0);
    await page
      .getByRole('region', { name: 'Brouillon à valider' })
      .getByRole('button', { name: 'Confirmer', exact: true })
      .click();
    const card = page.getByRole('region', { name: 'Générer', exact: true });
    await expect(card).toBeVisible();
    expect(attempts).toBe(0);
    const generate = card.getByRole('button', { name: 'Générer', exact: true });
    await generate.focus();
    await page.keyboard.press('Enter');
    await expect(generate).toHaveCount(0);
    if (lost)
      await expect(card.getByRole('status')).toContainText('Le résultat n’est pas encore confirmé');
    else {
      await expect(card.getByRole('textbox')).toHaveValue(secret);
      await expect(card.getByRole('textbox')).toBeFocused();
    }
    expect(attempts).toBe(1);
    expect(
      (await new AxeBuilder({ page }).include('section[aria-label="Générer"]').analyze()).violations
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    ).toBe(true);
    await page.reload();
    await waitForHydration(page, 'section[aria-label="Générer"] button');
    await expect(page.locator(`input[value="${secret}"]`)).toHaveCount(0);
    await expect(
      page
        .getByRole('region', { name: 'Générer', exact: true })
        .getByRole('button', { name: 'Générer', exact: true })
    ).toHaveCount(0);
    expect(attempts).toBe(1);
  });
}

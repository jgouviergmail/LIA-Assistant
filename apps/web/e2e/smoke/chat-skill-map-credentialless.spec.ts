/**
 * The real Next.js React renderer must keep `credentialless` on a trusted
 * interactive-map iframe. The standalone React used by Vitest used to retain
 * an empty-string prop that Next's boolean-attribute renderer drops.
 */
import { test, expect, type MockRoute } from '../fixtures';

const mapUrl = 'https://www.google.com/maps/embed?pb=e2e';
const widgetId = 'skill_app_map_e2e';

test.skip(({ browserName }) => browserName !== 'chromium', 'credentialless is Chromium-only');

const chatData: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me',
    json: {
      id: '00000000-0000-4000-8000-00000000c001',
      user_id: '00000000-0000-4000-8000-000000000001',
      title: 'Map fixture',
      message_count: 1,
      total_tokens: 0,
      created_at: '2026-09-21T09:00:00Z',
      updated_at: '2026-09-21T09:00:00Z',
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [
        {
          id: '00000000-0000-4000-8000-00000000a001',
          role: 'assistant',
          content: `<div class="lia-skill-app" data-registry-id="${widgetId}"></div>`,
          message_metadata: {
            widgets: {
              [widgetId]: {
                id: widgetId,
                type: 'SKILL_APP',
                payload: {
                  skill_name: 'interactive-map',
                  title: 'Map',
                  frame_url: mapUrl,
                  is_system_skill: true,
                },
                meta: { source: 'skill', timestamp: '2026-09-21T09:00:00Z' },
              },
            },
          },
          created_at: '2026-09-21T09:00:00Z',
          tokens_in: null,
          tokens_out: null,
          tokens_cache: null,
          cost_eur: null,
          google_api_requests: null,
          stt_provider: null,
        },
      ],
      conversation_id: '00000000-0000-4000-8000-00000000c001',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
];

test('trusted interactive-map keeps its credentialless iframe in Next.js Chromium', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await mockApi(chatData);
  await page.route('https://www.google.com/maps/embed?**', route =>
    route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Map fixture</title>' })
  );

  await page.goto('/en/dashboard/chat');

  const frame = page.locator('iframe.lia-skill-app-widget__iframe');
  await expect(frame).toHaveAttribute('src', mapUrl);
  await expect(frame).toHaveAttribute('sandbox', 'allow-scripts allow-popups allow-same-origin');
  // React may serialize the boolean attribute as "" or "true". Presence and
  // the browser property are the behavior that matters under COEP.
  await expect(frame).toHaveAttribute('credentialless', /.*/);
  const credentiallessEnabled = await frame.evaluate(
    element => 'credentialless' in element && element.credentialless === true
  );
  expect(credentiallessEnabled).toBe(true);
});

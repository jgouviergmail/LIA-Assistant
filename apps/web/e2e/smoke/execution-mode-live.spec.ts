/**
 * An automatic answer names its engine immediately, including with Telegram linked.
 *
 * The history stays empty until the live SSE badge has been observed, so a
 * background read cannot repair a missing `done.execution_engine` unnoticed.
 * Then the real notification stream announces the archived answer alongside a
 * new message: the history merges without replacing or duplicating the live
 * bubble. Telegram's linked/unlinked state is first verified in its settings.
 */
import {
  test,
  expect,
  chatRoutes,
  idleNotificationStream,
  waitForHydration,
  waitForMockGate,
  type MockRoute,
} from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';

const CONVERSATION_ID = '00000000-0000-4000-8000-00000000b390';
const QUESTION_ID = '00000000-0000-4000-8000-00000000b391';
const ANSWER_ID = '00000000-0000-4000-8000-00000000b392';
const ARRIVAL_ID = '00000000-0000-4000-8000-00000000b393';
const QUESTION = 'Summarize my next appointment.';
const ANSWER = 'Your next appointment is tomorrow at 10:00.';
const ARRIVAL = 'History synchronization reached this browser.';

const ENGINES = [
  { engine: 'pipeline', name: 'Pipeline', said: 'Automatic mode: answered by a Pipeline plan' },
  { engine: 'react', name: 'ReAct', said: 'Automatic mode: answered by the ReAct loop' },
] as const;

for (const { engine, name, said } of ENGINES) {
  for (const telegramActive of [false, true]) {
    test(`${name} appears on the fresh answer and survives sync with Telegram ${telegramActive ? 'active' : 'unlinked'}`, async ({
      page,
      authenticate,
      mockApi,
    }, testInfo) => {
      const user = await authenticate({ execution_mode: 'auto' });
      const time = Date.now();
      let archiveAvailable = false;
      const historyReads: boolean[] = [];
      const requests: unknown[] = [];
      const archived = [
        {
          id: ARRIVAL_ID,
          role: 'assistant',
          content: ARRIVAL,
          created_at: new Date(time + 2000).toISOString(),
          message_metadata: {},
        },
        {
          id: ANSWER_ID,
          role: 'assistant',
          content: ANSWER,
          created_at: new Date(time + 1000).toISOString(),
          message_metadata: { run_id: 'e2e-auto-live', execution_engine: engine },
        },
        {
          id: QUESTION_ID,
          role: 'user',
          content: QUESTION,
          created_at: new Date(time).toISOString(),
          message_metadata: { run_id: 'e2e-auto-live' },
        },
      ];
      await mockApi([
        ...chatRoutes([]),
        {
          url: '**/api/v1/config',
          json: { ...appConfig, features: { ...appConfig.features, channels_enabled: true } },
        },
        {
          url: '**/api/v1/auth/me/execution-mode-preference',
          json: { execution_mode: 'auto', auto_resolution: 'decided' },
        },
        {
          url: '**/api/v1/channels',
          json: {
            bindings: telegramActive
              ? [
                  {
                    id: '00000000-0000-4000-8000-00000000b394',
                    channel_type: 'telegram',
                    channel_user_id: 'synthetic-telegram-account',
                    channel_username: 'e2e_account',
                    is_active: true,
                    created_at: new Date(time).toISOString(),
                    updated_at: new Date(time).toISOString(),
                  },
                ]
              : [],
            total: telegramActive ? 1 : 0,
            telegram_bot_username: 'SyntheticLiaBot',
          },
        },
        {
          url: '**/api/v1/conversations/me',
          json: {
            id: CONVERSATION_ID,
            user_id: user.id,
            title: 'E2E automatic answer',
            message_count: 0,
            total_tokens: 0,
            created_at: new Date(time).toISOString(),
            updated_at: new Date(time).toISOString(),
          },
        },
        {
          url: '**/api/v1/conversations/me/messages*',
          handler: async route => {
            historyReads.push(archiveAvailable);
            await route.fulfill({
              json: {
                messages: archiveAvailable ? archived : [],
                conversation_id: CONVERSATION_ID,
                total_count: archiveAvailable ? archived.length : 0,
                has_more: false,
                next_cursor: null,
              },
            });
          },
        },
        {
          url: '**/api/v1/agents/chat/stream',
          method: 'POST',
          handler: async route => {
            requests.push(route.request().postDataJSON());
            const chunks = [
              { type: 'token', content: ANSWER, metadata: { run_id: 'e2e-auto-live' } },
              {
                type: 'done',
                content: '',
                metadata: {
                  run_id: 'e2e-auto-live',
                  execution_engine: engine,
                  archived_message_id: ANSWER_ID,
                  archived_user_message_id: QUESTION_ID,
                },
              },
            ];
            await route.fulfill({
              contentType: 'text/event-stream',
              body: chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join(''),
            });
          },
        },
      ]);

      // This makes the channel matrix observable, rather than an unused mock.
      await page.goto('/en/dashboard/settings?section=channels');
      const channels = page.locator('#settings-section-channels');
      await expect(channels).toBeVisible();
      if (telegramActive) {
        await expect(
          channels.getByRole('switch', { name: 'Enable/disable channel' })
        ).toBeChecked();
        await expect(channels.getByText('Active', { exact: true })).toBeVisible();
      } else {
        await expect(
          channels.getByRole('button', { name: 'Link Telegram', exact: true })
        ).toBeVisible();
        await expect(channels.getByRole('switch')).toHaveCount(0);
      }

      const { promise: changed, resolve: announceArchive } = Promise.withResolvers<void>();
      let signalled = false;
      const notifications: MockRoute = {
        url: '**/api/v1/notifications/stream',
        handler: async (route, signal) => {
          if (signalled) {
            await idleNotificationStream.handler?.(route, signal);
            return;
          }
          if (!(await waitForMockGate(changed, signal))) return;
          signalled = true;
          await route.fulfill({
            contentType: 'text/event-stream',
            body:
              'event: notification\n' +
              `data: ${JSON.stringify({ type: 'conversation_updated', conversation_id: CONVERSATION_ID })}\n\n`,
          });
        },
      };
      await mockApi([notifications]);
      await page.goto('/en/dashboard/chat');
      await waitForHydration(page, 'textarea');
      await expect(
        page
          .locator('header')
          .getByRole('button', { name: 'Execution: Automatic mode', exact: true })
      ).toBeVisible();
      await expect.poll(() => historyReads.length).toBeGreaterThan(0);
      await expect(page.locator('[data-execution-engine]')).toHaveCount(0);

      await page.locator('textarea').fill(QUESTION);
      await page.locator('textarea').press('Enter');

      const answer = page.locator('.message-bubble-assistant').filter({ hasText: ANSWER });
      await expect(answer).toBeVisible();
      const meta = answer.locator('xpath=following-sibling::span[1]');
      const badge = meta.locator(`[data-execution-engine="${engine}"]`);
      await expect(badge.getByText(name, { exact: true })).toBeVisible();
      await expect(badge).toHaveAttribute('title', said);
      await expect(meta).toContainText(`| ${name}`);
      expect(requests).toHaveLength(1);
      expect(requests[0]).toMatchObject({ message: QUESTION });
      expect(historyReads.every(available => !available)).toBe(true);
      await answer.evaluate(node => node.setAttribute('data-e2e-live-answer', 'kept'));
      await badge.evaluate(node => node.setAttribute('data-e2e-live-badge', 'kept'));
      await testInfo.attach('fresh-sse-badge', {
        body: await page.screenshot(),
        contentType: 'image/png',
      });

      archiveAvailable = true;
      announceArchive();

      await expect(page.getByText(ARRIVAL, { exact: true })).toBeVisible();
      expect(historyReads).toContain(true);
      await expect(answer).toHaveCount(1);
      await expect(page.getByText(QUESTION, { exact: true })).toHaveCount(1);
      await expect(page.locator('[data-execution-engine]')).toHaveCount(1);
      await expect(page.locator('[data-e2e-live-answer="kept"]')).toHaveCount(1);
      await expect(page.locator('[data-e2e-live-badge="kept"]')).toHaveCount(1);
      await expect(badge.getByText(name, { exact: true })).toBeVisible();
      await expect(badge).toHaveAttribute('title', said);
      await testInfo.attach('badge-after-history-sync', {
        body: await page.screenshot(),
        contentType: 'image/png',
      });
    });
  }
}

/** Selection proposals reach native forms without a provider write before explicit Save. */
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import type { CreationProposal } from '../../src/lib/selection-assist/contracts';

const SOURCE =
  'Meet Ana on 12 November at 14:30, prepare the notes, and remember that I prefer green tea.';
const CALENDAR = {
  id: 'primary',
  name: 'My calendar',
  primary: true,
  writable: true,
  manageable: false,
  color: '#7c3aed',
};
const OFFER = {
  text_max_chars: 8000,
  question_max_chars: 500,
  language_max_chars: 40,
  internet_available: true,
  read_aloud_available: true,
  internet_timeout_seconds: 360,
  call_timeout_seconds: 120,
  heartbeat_seconds: 10,
  destinations: ['task', 'event', 'memory', 'reminder', 'ticket'],
};
const ROUTES: MockRoute[] = [
  {
    url: '**/api/v1/config',
    json: {
      ...appConfig,
      features: { ...appConfig.features, workbench_enabled: true, workboard_enabled: true },
      capabilities: {
        workbench: { enabled: true, family: 'work' },
        tool_assists: { enabled: true, family: 'work' },
        memory: { enabled: true, family: 'personal' },
        workboard: { enabled: true, family: 'work' },
      },
    },
  },
  { url: '**/api/v1/tool-assists/selection', json: OFFER },
  {
    url: '**/api/v1/conversations/me',
    json: {
      id: 'conversation',
      user_id: '00000000-0000-4000-8000-000000000001',
      title: 'Review',
      message_count: 1,
      total_tokens: 0,
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [
        {
          id: 'message',
          role: 'assistant',
          content: `<p>${SOURCE}</p>`,
          created_at: '2026-11-09T10:00:00Z',
          message_metadata: null,
        },
      ],
      conversation_id: 'conversation',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
  {
    url: '**/api/v1/workbench',
    json: {
      tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool => ({
        tool,
        state: ['tasks', 'calendar'].includes(tool) ? 'ready' : 'not_connected',
        provider:
          tool === 'tasks' ? 'google_tasks' : tool === 'calendar' ? 'google_calendar' : null,
        features: tool === 'tasks' ? ['due_date_only'] : [],
        bounds: {
          title_max_chars: 1024,
          notes_max_chars: 8192,
          summary_max_chars: 1024,
          description_max_chars: 8192,
        },
      })),
      limits: {
        page_size: 25,
        bulk_max_items: 50,
        download_max_bytes: 1,
        upload_max_bytes: 1,
        calendar_window_max_events: 500,
        send_undo_seconds: 0,
        draft_autosave_seconds: 0,
        search_max_chars: 500,
        assist_text_max_chars: 8000,
        assist_instruction_max_chars: 500,
      },
    },
  },
  {
    url: '**/api/v1/workbench/tasks/lists*',
    method: 'GET',
    json: {
      items: [
        { id: 'home', title: 'Home', default: true },
        { id: 'work', title: 'Work', default: false },
      ],
      next_page_token: null,
    },
  },
  { url: '**/api/v1/workbench/tasks?*', method: 'GET', json: { items: [], next_page_token: null } },
  {
    url: '**/api/v1/workbench/tasks/due?*',
    method: 'GET',
    json: { tasks: [], truncated: false, failed: [] },
  },
  { url: '**/api/v1/workbench/calendar/calendars', method: 'GET', json: { calendars: [CALENDAR] } },
  {
    url: '**/api/v1/workbench/calendar/events?*',
    method: 'GET',
    json: {
      calendars: [
        { calendar_id: 'primary', events: [], truncated: false, skipped: 0, error: null },
      ],
    },
  },
  {
    url: '**/api/v1/memories',
    method: 'GET',
    json: {
      items: [],
      total: 0,
      by_category: {},
      limits: {
        content_min_chars: 3,
        content_max_chars: 500,
        trigger_topic_max_chars: 100,
        usage_nuance_max_chars: 300,
      },
    },
  },
  { url: '**/api/v1/memories/categories', method: 'GET', json: { categories: [] } },
  { url: '**/api/v1/reminders/detail*', method: 'GET', json: { reminders: [], total: 0 } },
  {
    url: '**/api/v1/workboard/tickets*',
    method: 'GET',
    json: { tickets: [], total: 0, counts_by_status: {}, page_size: 25 },
  },
];

test('pending audio stays compact, announces its act and respects reduced motion', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await authenticate({ language: 'fr' });
  let release: () => void = () => undefined;
  const pending = new Promise<void>(resolve => {
    release = resolve;
  });
  await mockApi([
    ...ROUTES,
    {
      url: '**/api/v1/tool-assists/read-aloud',
      method: 'POST',
      handler: async route => {
        await pending;
        await route.fulfill({
          json: {
            audio: readFileSync(resolve('../public/world/audio/v1/message.mp3')).toString('base64'),
            cut: false,
            cost_eur: 0.002,
            usage: null,
          },
        });
      },
    },
  ]);
  try {
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page, 'main');
    await page.getByText(SOURCE, { exact: true }).evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
    await page
      .getByRole('toolbar', { name: 'Demander à LIA sur ce texte' })
      .getByRole('button', { name: 'Lire', exact: true })
      .click();
    const bubble = page.getByRole('dialog', { name: 'Lire', exact: true });
    const status = bubble.getByRole('status');
    await expect(status).toHaveText('LIA prépare la lecture…');
    await expect(status).toHaveAttribute('aria-busy', 'true');
    const spinner = status.locator('svg');
    await expect(spinner).toHaveCSS('animation-name', 'spin');
    await expect
      .poll(() => bubble.evaluate(element => element.scrollWidth - element.clientWidth))
      .toBeLessThanOrEqual(1);
    expect(
      (await new AxeBuilder({ page }).include('[data-selection-assist-ui]').analyze()).violations
    ).toEqual([]);
    await bubble.screenshot({ path: testInfo.outputPath('waiting-audio.png') });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(spinner).toHaveCSS('animation-name', 'none');
    release();
    await expect(bubble.locator('audio')).toBeVisible();
    await expect(status).toHaveCount(0);
  } finally {
    release();
  }
});

test('reading, summarizing and handing words to LIA keep their own reviewed paths', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate();
  const spoken: unknown[] = [],
    asked: unknown[] = [],
    sent: unknown[] = [];
  await mockApi([
    ...ROUTES,
    {
      url: '**/api/v1/tool-assists/read-aloud',
      method: 'POST',
      handler: async route => {
        spoken.push(route.request().postDataJSON());
        await route.fulfill({
          json: {
            audio: readFileSync(resolve('../public/world/audio/v1/message.mp3')).toString('base64'),
            cut: true,
            cost_eur: 0.002,
            usage: null,
          },
        });
      },
    },
    {
      url: '**/api/v1/tool-assists/text/selection/stream',
      method: 'POST',
      handler: async route => {
        asked.push(route.request().postDataJSON());
        await route.fulfill({
          contentType: 'text/event-stream',
          body: `data: ${JSON.stringify({ result: { proposal: { kind: 'text', text: 'Meet Ana and prepare the notes.' }, usage: null } })}\n\n`,
        });
      },
    },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        sent.push(route.request().postDataJSON());
        await route.fulfill({ contentType: 'text/event-stream', body: '' });
      },
    },
  ]);
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page, 'main');
  const choose = async (name: string) => {
    const passage = page.getByText(SOURCE, { exact: true });
    // A new pointer gesture re-arms a source dismissed after the previous action.
    await passage.click();
    await passage.evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
    await page
      .getByRole('toolbar', { name: 'Ask LIA about this text' })
      .getByRole('button', { name, exact: true })
      .click();
  };
  await choose('Read');
  const reading = page.getByRole('dialog', { name: 'Read', exact: true });
  const audio = reading.locator('audio');
  await expect(audio).toHaveAttribute('controls', '');
  await expect(reading.getByText('Only the beginning is read.')).toBeVisible();
  expect(spoken).toEqual([{ text: SOURCE }]);
  await expect
    .poll(() =>
      audio.evaluate(element => {
        if (!(element instanceof HTMLAudioElement))
          throw new Error('Expected the native audio player');
        return element.readyState;
      })
    )
    .toBeGreaterThan(0);
  await reading.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.locator('audio[aria-label="Read"]')).toHaveCount(0);
  await choose('Summarize');
  const summary = page.getByRole('dialog', { name: 'Summarize', exact: true });
  await expect(summary.getByText('Meet Ana and prepare the notes.')).toBeVisible();
  expect(asked).toEqual([{ mode: 'read', action: 'summarize', text: SOURCE, origin: 'page' }]);
  await summary.getByRole('button', { name: 'Close', exact: true }).click();
  await choose('LIA');
  await waitForHydration(page, 'main');
  await expect(page.getByRole('textbox', { name: 'Type your message...' })).toHaveValue(SOURCE);
  expect(page.url()).not.toContain('Ana');
  expect(sent).toEqual([]);
});
const CASES: {
  proposal: CreationProposal;
  action: string;
  path: string;
  dialog: string;
  field: string;
  initial: string;
  save: string;
  endpoint: string;
}[] = [
  {
    proposal: {
      kind: 'reminder',
      reminder: {
        content: 'Call Ana',
        recurrence: {
          freq: 'once',
          anchor_date: '2030-11-12',
          interval: 1,
          byweekday: [],
          bymonthday: [],
          bymonth: [],
          nth_weekday: null,
          times: {
            mode: 'at',
            at: [{ hour: 9, minute: 0 }],
            step_minutes: null,
            start: null,
            end: null,
          },
          end: { kind: 'never', on_date: null, after_count: null },
        },
      },
    },
    action: 'Reminder',
    path: '/en/dashboard/settings?section=reminders',
    dialog: 'New reminder',
    field: 'Remind me to',
    initial: 'Call Ana',
    save: 'Save',
    endpoint: '/reminders',
  },
  {
    proposal: { kind: 'ticket', ticket: { title: 'Call Ana', description: 'Ask about the quote' } },
    action: 'Ticket',
    path: '/en/dashboard/workboard',
    dialog: 'New ticket',
    field: 'Title',
    initial: 'Call Ana',
    save: 'New ticket',
    endpoint: '/workboard/tickets',
  },
  {
    proposal: {
      kind: 'task',
      task: {
        title: 'Prepare the notes',
        notes: 'For Ana',
        due: '2026-11-12',
        list_name: 'Work',
        importance: null,
      },
    },
    action: 'Task',
    path: '/en/dashboard/tools/tasks',
    dialog: 'New task',
    field: 'Title',
    initial: 'Prepare the notes',
    save: 'Add',
    endpoint: '/workbench/tasks',
  },
  {
    proposal: {
      kind: 'event',
      event: {
        summary: 'Meet Ana',
        start_date: '2026-11-12',
        start_time: '14:30',
        end_date: '2026-11-12',
        end_time: '15:00',
        all_day: false,
        location: 'Office',
        description: 'Bring the notes',
        attendees: [],
        repeat: 'none',
        conference: false,
      },
    },
    action: 'Event',
    path: '/en/dashboard/tools/calendar',
    dialog: 'New event',
    field: 'Title',
    initial: 'Meet Ana',
    save: 'Create',
    endpoint: '/workbench/calendar/events',
  },
  {
    proposal: {
      kind: 'memory',
      memory: {
        content: 'Prefers green tea',
        category: 'preference',
        emotional_weight: 0,
        importance: 0.6,
        usage_nuance: 'When choosing a drink',
        trigger_topic: 'tea',
      },
    },
    action: 'Remember',
    path: '/en/dashboard/settings?section=memories',
    dialog: 'Create a memory',
    field: 'Content *',
    initial: 'Prefers green tea',
    save: 'Create',
    endpoint: '/memories',
  },
];

for (const sample of CASES) {
  test(`${sample.proposal.kind} is reviewed in its native form before saving`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ timezone: 'Europe/Paris', memory_enabled: true });
    await mockApi(ROUTES);
    const asks: unknown[] = [],
      writes: Record<string, unknown>[] = [];
    await mockApi([
      {
        url: '**/api/v1/tool-assists/text/selection/stream',
        method: 'POST',
        handler: async route => {
          asks.push(route.request().postDataJSON());
          await route.fulfill({
            contentType: 'text/event-stream',
            body:
              'data: ' +
              JSON.stringify({
                result: {
                  proposal: sample.proposal,
                  usage: {
                    tokens_in: 30,
                    tokens_out: 15,
                    tokens_cache: 0,
                    cost_eur: 0.001,
                    model_name: 'test',
                  },
                },
              }) +
              '\n\n',
          });
        },
      },
      {
        url: '**/api/v1' + sample.endpoint,
        method: 'POST',
        handler: async route => {
          const body: Record<string, unknown> = route.request().postDataJSON();
          writes.push(body);
          await route.fulfill({
            status: 201,
            json: {
              ...body,
              id: 'created',
              pinned: false,
              created_at: '2026-11-09T10:00:00Z',
              updated_at: '2026-11-09T10:00:00Z',
            },
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/chat');
    await expect(page.getByText(SOURCE, { exact: true })).toBeVisible();
    await waitForHydration(page, 'main');
    await page.getByText(SOURCE, { exact: true }).evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
    const toolbar = page.getByRole('toolbar', { name: 'Ask LIA about this text' });
    await expect(toolbar).toBeVisible();
    await toolbar.getByRole('button', { name: sample.action, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(sample.path.replaceAll('?', '\\?') + '$'));
    expect(page.url()).not.toContain('Ana');
    const form = page.getByRole('dialog', { name: sample.dialog, exact: true });
    await expect(form).toBeVisible();
    const field = form.getByRole('textbox', { name: sample.field, exact: true });
    await expect(field).toHaveValue(sample.initial);
    expect(writes).toEqual([]);
    expect(asks).toHaveLength(1);
    expect(asks[0]).toMatchObject({ mode: 'read', action: sample.proposal.kind, text: SOURCE });
    if (sample.proposal.kind === 'task')
      await expect(form.getByRole('combobox', { name: 'List' })).toHaveValue('work');
    await field.fill(sample.initial + ' — reviewed');
    expect(
      (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations
    ).toEqual([]);
    await form.getByRole('button', { name: sample.save, exact: true }).click();
    await expect(form).not.toBeVisible();
    expect(writes).toHaveLength(1);
    const contentField =
      sample.proposal.kind === 'memory' || sample.proposal.kind === 'reminder'
        ? 'content'
        : sample.proposal.kind === 'task' || sample.proposal.kind === 'ticket'
          ? 'title'
          : 'summary';
    expect(writes[0][contentField]).toBe(sample.initial + ' — reviewed');
  });
}

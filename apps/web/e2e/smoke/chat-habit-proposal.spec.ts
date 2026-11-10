/**
 * The habit proposal card in the chat (ADR-375).
 *
 * The server shows at most one proposal under an answer, chosen by code, and
 * carries it in the answer's metadata (`habit_proposal`) — archived for a
 * reload, and in the `done` chunk for the live answer. The unit tests pin who
 * may take the band and which value reads as a proposal; this spec pins it in a
 * real browser, on a phone: the card takes the chips' place, accepting it calls
 * the decision route and says so, the card leaves, the chips come back and the
 * focus returns to the composer; and a live answer brings its card at once.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { test, expect, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow } from './overflow-report';

const french: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);

/** Shipped French copy, never a copy of it in the harness. */
function copy(key: string): string {
  let value: unknown = french;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = Object.entries(value).find(([name]) => name === part)?.[1];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value;
}

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0a1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E habit proposal',
  message_count: 1,
  total_tokens: 0,
  created_at: '2026-11-08T09:00:00Z',
  updated_at: '2026-11-08T09:00:00Z',
};

const PROPOSAL = {
  id: '00000000-0000-4000-8000-0000000000a1',
  kind: 'automate_need',
  key: 'weather',
  facts: {
    domain: 'weather',
    cadence: 'weekdays',
    weekday: null,
    hour: 7,
    minute: 30,
    distinct_days: 14,
    active_days: 22,
    part_of_day: 'morning',
    existing_routine: null,
  },
  created_at: '2026-11-01T03:00:00Z',
  updated_at: '2026-11-08T03:00:00Z',
};

const SUGGESTION = 'Et pour demain ?';

/** `message_metadata` is the alias the API serialises and `useConversation` maps. */
const ANSWER = {
  id: '00000000-0000-4000-8000-00000000m0a1',
  role: 'assistant',
  content: '<p>Il fera beau ce matin.</p>',
  created_at: '2026-11-08T09:00:00Z',
  message_metadata: { habit_proposal: PROPOSAL, followup_suggestions: [SUGGESTION] },
};

function routes(messages: unknown[], decisions: string[]): MockRoute[] {
  return [
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages,
        conversation_id: CONVERSATION.id,
        total_count: messages.length,
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
      url: '**/api/v1/habits/proposals/*/*',
      method: 'POST',
      handler: async route => {
        const [id, verdict] = new URL(route.request().url()).pathname.split('/').slice(-2);
        decisions.push(`${id}/${verdict}`);
        await route.fulfill({
          json: { id, kind: PROPOSAL.kind, status: 'accepted', routine_id: null },
        });
      },
    },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'data: {"type":"token","content":"Il fera beau ce matin.","metadata":null}\n\n' +
            `data: ${JSON.stringify({ type: 'done', content: '', metadata: { habit_proposal: PROPOSAL } })}\n\n`,
        });
      },
    },
  ];
}

test.describe('the habit proposal card in the chat', () => {
  test('takes the chips’ place, and accepting it carries it out and gives them back', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ language: 'fr' });
    const decisions: string[] = [];
    await mockApi(routes([ANSWER], decisions));
    await page.goto('/fr/dashboard/chat');

    const card = page.getByRole('region', { name: copy('habits.proposals.chat_title') });
    await expect(card).toBeVisible();
    // The sentence is phrased from the facts, in the reader's language.
    await expect(card.getByText('07:30', { exact: false })).toBeVisible();
    // One question at a time: the chips wait for the decision.
    await expect(page.getByRole('button', { name: SUGGESTION })).toHaveCount(0);
    await expectNoOverflow(page, 'chat proposal card');
    const accessibility = await scanPage(page, testInfo, 'chat-habit-proposal');
    expect(accessibility.blocking, accessibility.summary).toHaveLength(0);

    await card
      .getByRole('button', { name: copy('habits.proposals.automate_need.accept'), exact: true })
      .click();

    await expect.poll(() => decisions).toEqual([`${PROPOSAL.id}/accept`]);
    await expect(page.getByText(copy('habits.proposals.automate_need.done'))).toBeVisible();
    await expect(card).toHaveCount(0);
    await expect(page.getByRole('button', { name: SUGGESTION })).toBeVisible();
    await expect(page.locator('[data-chat-composer]')).toBeFocused();
  });

  test('a live answer brings its card in its done chunk', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(routes([], []));
    await page.goto('/fr/dashboard/chat');

    const composer = page.locator('[data-chat-composer]');
    await composer.fill('Quel temps fera-t-il ?');
    await composer.press('Enter');

    await expect(page.getByText('Il fera beau ce matin.')).toBeVisible();
    await expect(
      page.getByRole('region', { name: copy('habits.proposals.chat_title') })
    ).toBeVisible();
  });
});

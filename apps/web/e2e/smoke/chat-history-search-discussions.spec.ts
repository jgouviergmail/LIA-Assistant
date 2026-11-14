/**
 * The history search reaches every discussion of the account (lot 12).
 *
 * From Main, the words are found in an annex: the result names its discussion,
 * opening it lands on the page ending at the message, the words marked, and
 * the keyboard user is left on the switcher, which now names the annex. A
 * result of the discussion on screen names none and stays a jump in place.
 */
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { test, expect } from '../fixtures';
import { ANNEX_DISCUSSION_ID, MAIN_DISCUSSION_ID, discussionFixture } from '../fixtures/discussions';
import type { DiscussionSearchResult } from '../../src/hooks/useConversation';

const fr = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
) as {
  conversations: { search_placeholder: string };
  chat: { search: Record<string, string> };
};
const copy = fr.chat.search;

const IN_ANNEX: DiscussionSearchResult = {
  message_id: '00000000-0000-4000-8000-0000000000f1',
  role: 'assistant',
  content: 'Le devis de la toiture est arrivé',
  created_at: '2026-11-08T09:30:00Z',
  conversation_id: ANNEX_DISCUSSION_ID,
  conversation_kind: 'secondary',
  conversation_title: 'Travaux',
  conversation_revision: 0,
};
const IN_MAIN: DiscussionSearchResult = {
  ...IN_ANNEX,
  message_id: '00000000-0000-4000-8000-0000000000f2',
  content: 'Relance le devis demain',
  created_at: '2026-11-07T08:00:00Z',
  conversation_id: MAIN_DISCUSSION_ID,
  conversation_kind: 'main',
  conversation_title: 'Conversation du 9 novembre',
};

test('a word found in another discussion opens it at the message, the word marked', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id, { annexTitle: 'Travaux' });
  const searches: URLSearchParams[] = [];
  const jumps: URLSearchParams[] = [];
  await mockApi([
    ...fixture.routes,
    {
      url: '**/api/v1/conversations/me/search?*',
      method: 'GET',
      handler: async route => {
        searches.push(new URL(route.request().url()).searchParams);
        await route.fulfill({
          json: { results: [IN_ANNEX, IN_MAIN], has_more: false, next_cursor: null },
        });
      },
    },
    {
      // The page ENDING at the message a jump asks for; any other page is the fixture's.
      url: '**/api/v1/conversations/me/messages*',
      handler: async route => {
        const query = new URL(route.request().url()).searchParams;
        if (!query.has('before')) {
          await route.fallback();
          return;
        }
        jumps.push(query);
        await route.fulfill({
          json: {
            conversation_id: ANNEX_DISCUSSION_ID,
            messages: [
              {
                id: IN_ANNEX.message_id,
                role: IN_ANNEX.role,
                content: IN_ANNEX.content,
                created_at: IN_ANNEX.created_at,
              },
            ],
            total_count: 1,
            has_more: false,
            next_cursor: null,
          },
        });
      },
    },
  ]);
  await page.goto('/fr/dashboard/chat');
  await expect(page.getByText('Historique principal')).toBeVisible();

  await page.getByRole('searchbox', { name: fr.conversations.search_placeholder }).fill('devis');
  // Everything of Main is loaded, but another discussion exists: the server is offered.
  const searchAll = page.getByRole('button', { name: copy.search_all });
  await searchAll.click();
  await expect(page.getByText(copy.remote_count_other.replace('{{count}}', '2'))).toBeVisible();
  expect(searches).toHaveLength(1);
  expect(Object.fromEntries(searches[0])).toEqual({ q: 'devis', limit: '20' });

  // The annex's result names its discussion; Main's, the one on screen, names none.
  const annexResult = page.getByRole('button', {
    name: /^Ouvrir la discussion Travaux à ce message du /,
  });
  await expect(annexResult).toContainText(copy.in_discussion.replace('{{name}}', 'Travaux'));
  const mainResult = page.getByRole('button', { name: /^Ouvrir la conversation à ce message du / });
  await expect(mainResult).not.toContainText('dans ');
  expect(
    (
      await new AxeBuilder({ page })
        .include('ul[role="list"]')
        .withTags(['wcag2a', 'wcag2aa'])
        .analyze()
    ).violations
  ).toEqual([]);

  // Keyboard: the annex opens, and the switcher that names it holds the focus.
  await annexResult.focus();
  await page.keyboard.press('Enter');
  const annexBadge = page.getByRole('button', { name: 'Discussions — Travaux', exact: true });
  await expect(annexBadge).toBeFocused();
  await expect(page.getByText(copy.history_view)).toBeVisible();
  await expect(page.locator('mark.lia-search-mark', { hasText: 'devis' })).toBeVisible();
  await expect(page.getByText('Historique annexe')).toHaveCount(0);
  // The page asked for ends at the message: its instant plus one millisecond.
  expect(jumps).toHaveLength(1);
  expect(jumps[0].get('before')).toBe('2026-11-08T09:30:00.001Z');
  expect(jumps[0].get('conversation_id')).toBe(ANNEX_DISCUSSION_ID);

  // Back to the annex's present, from the banner (the floating return button
  // beside the list bears the same name and does the same).
  const banner = page.getByText(copy.history_view).locator('..');
  await banner.getByRole('button', { name: copy.back_to_present }).click();
  await expect(page.getByText('Historique annexe')).toBeVisible();
  await expect(page.getByText(copy.history_view)).toHaveCount(0);
});

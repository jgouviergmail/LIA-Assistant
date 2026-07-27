/**
 * Chat surface priority (S1) — comfort surfaces yield to a pending action.
 *
 * Measured context (S0, 2026-07-26): with a pending HITL card AND follow-up
 * chips, the chat chrome reached 443 px of a 716 px shell — 62 %, leaving four
 * lines of conversation on a small phone. The height was the symptom; the
 * defect was the combination: LIA asked the user to confirm sending an email
 * while, one row above, offering three unrelated follow-up questions.
 *
 * `lib/chat-surfaces` now arbitrates. This spec proves the rule end to end in a
 * real browser — the unit tests pin the decision table, this pins that the
 * decision reaches the DOM and that the chips come back once the card is gone.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0s1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E surface priority',
  message_count: 1,
  total_tokens: 0,
  created_at: '2026-07-26T09:00:00Z',
  updated_at: '2026-07-26T10:00:00Z',
};

const SUGGESTIONS = [
  'Déplace le rendez-vous de mardi',
  'Envoie un récapitulatif à l’équipe',
  'Ajoute un rappel une heure avant',
];

/**
 * The metadata key MUST be `message_metadata` — the Pydantic alias the API
 * serialises and the only one `useConversation` maps into `Message.metadata`.
 * A mock using `metadata` silently drops the suggestions (caught during S0).
 */
const ANSWER_WITH_FOLLOWUPS = {
  id: '00000000-0000-4000-8000-00000000m0s1',
  role: 'assistant',
  content: '<p>Voici vos prochains rendez-vous.</p>',
  created_at: '2026-07-26T10:00:00Z',
  message_metadata: { followup_suggestions: SUGGESTIONS },
};

const PENDING_HITL = {
  message_id: 'hitl_s1_1',
  action_requests: [
    {
      type: 'tool_confirmation',
      tool_name: 'send_email_tool',
      tool_args: { to: 'equipe@example.com', subject: 'Récapitulatif' },
      available_actions: [
        { action: 'confirm', label: 'confirm', style: 'primary' },
        { action: 'cancel', label: 'cancel', style: 'destructive' },
      ],
      registry_ids: [],
    },
  ],
  interrupt_ts: '2026-07-26T10:00:00+00:00',
  generated_question: "Confirmer l'envoi de cet e-mail ?",
};

function routes(pending: unknown): MockRoute[] {
  return [
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [ANSWER_WITH_FOLLOWUPS],
        conversation_id: CONVERSATION.id,
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: pending },
    { url: '**/api/v1/usage/**', json: {} },
  ];
}

test.describe('chat surface priority', () => {
  test('follow-up chips yield while an approval card awaits an answer', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(routes(PENDING_HITL));
    await page.goto('/fr/dashboard/chat');

    // The blocking surface is there… (same locator as chat-hitl-card.spec —
    // the card is identified by its landmark, not by its generated question).
    const card = page.locator('section[aria-label="Approbation requise"]');
    await expect(card).toBeVisible();
    await expect(card.getByText('send_email_tool')).toBeVisible();

    // …and every comfort chip stands down.
    for (const suggestion of SUGGESTIONS) {
      await expect(
        page.getByRole('button', { name: suggestion }),
        `chip "${suggestion}" must not compete with the pending approval`
      ).toHaveCount(0);
    }
  });

  test('the same answer shows its chips when no approval is pending', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Same message, same suggestions — only the pending interrupt differs. This
    // is what proves the previous test measured the RULE and not a broken mock.
    await authenticate({ language: 'fr' });
    await mockApi(routes(null));
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByRole('button', { name: SUGGESTIONS[0] })).toBeVisible();
    for (const suggestion of SUGGESTIONS) {
      await expect(page.getByRole('button', { name: suggestion })).toBeVisible();
    }
  });

  test('a chip prefills the composer without sending', async ({ page, authenticate, mockApi }) => {
    // The A2 contract must survive the arbitration rewiring.
    await authenticate({ language: 'fr' });
    await mockApi(routes(null));
    await page.goto('/fr/dashboard/chat');

    await page.getByRole('button', { name: SUGGESTIONS[1] }).click();
    await expect(page.locator('textarea').first()).toHaveValue(SUGGESTIONS[1]);
    // Nothing was sent: the answer is still the only assistant message.
    await expect(page.getByText('Voici vos prochains rendez-vous.')).toBeVisible();
  });
});

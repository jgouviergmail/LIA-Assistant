/**
 * Chat journey — words written while LIA answers wait for their turn (ADR-384),
 * or join the answer in progress (ADR-385).
 *
 * Hermetic: the answer is a mocked stream held open by a test gate (the page
 * is « answering » until it is released), and the waiting message's doors are
 * mocked routes that record what the page asked. The oracle is what the person
 * sees and what the page sent — never a component's internals.
 */
import {
  test,
  expect,
  waitForHydration,
  waitForMockGate,
  chatRoutes,
  type ChatBody,
  type MockRoute,
} from '../fixtures';
import type { WaitingMessage } from '@/lib/waiting-message';

interface WaitingBody {
  message?: string;
  version?: number;
  behind_stream_id?: string;
}

const NOW = '2026-11-13T15:00:00Z';

function waiting(content: string, overrides: Partial<WaitingMessage> = {}): WaitingMessage {
  return {
    conversation_id: '00000000-0000-4000-8000-0000000000ff',
    conversation_revision: 0,
    content,
    status: 'waiting',
    version: 1,
    send_requested: false,
    stream_id: null,
    can_join: false,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

/** The answer held open until `gate` resolves; the waiting doors recording their bodies. */
function waitingRoutes(
  state: {
    bodies: ChatBody[];
    kept: WaitingBody[];
    edits: WaitingBody[];
    withdrawn: number;
    current: ReturnType<typeof waiting> | null;
    refuse: boolean;
    joins: WaitingBody[];
    joinable: boolean;
    noteClosed: boolean;
  },
  gate: Promise<void>
): MockRoute[] {
  return [
    ...chatRoutes(state.bodies),
    // The discussion the waiting message belongs to, as the page loads it.
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: '00000000-0000-4000-8000-0000000000ff',
        user_id: '00000000-0000-4000-8000-000000000001',
        kind: 'main',
        revision: 0,
        title: 'E2E waiting message',
        message_count: 0,
        total_tokens: 0,
        created_at: NOW,
        updated_at: NOW,
      },
    },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async (route, signal) => {
        state.bodies.push((route.request().postDataJSON() ?? {}) as ChatBody);
        if (!(await waitForMockGate(gate, signal))) return;
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'data: {"type":"token","content":"Voici le point.","metadata":null}\n\n' +
            'data: {"type":"done","content":"","metadata":null}\n\n',
        });
      },
    },
    {
      url: '**/api/v1/agents/chat/waiting*',
      handler: async route => {
        const method = route.request().method();
        if (method === 'GET') {
          // Nothing waiting is the JSON `null`, typed as the API types it:
          // `json: null` would leave the type out, and the client would read
          // the TEXT « null » — a waiting message made of nothing.
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(state.current),
          });
          return;
        }
        if (method === 'POST') {
          const body = (route.request().postDataJSON() ?? {}) as WaitingBody;
          state.kept.push(body);
          if (state.refuse) {
            await route.fulfill({
              status: 409,
              json: {
                detail: {
                  error: 'waiting_message_departing',
                  message:
                    'Ton message en attente est en train de partir. Réessaie dans un instant.',
                },
              },
            });
            return;
          }
          const previous = state.current?.content;
          const content = previous ? `${previous}\n\n${body.message}` : String(body.message);
          state.current = waiting(content, {
            version: (state.current?.version ?? 0) + 1,
            can_join: state.joinable,
          });
          await route.fulfill({
            status: 200,
            json: { waiting: state.current, departed: false, stream_id: null },
          });
          return;
        }
        if (method === 'PUT') {
          const body = (route.request().postDataJSON() ?? {}) as WaitingBody;
          state.edits.push(body);
          state.current = waiting(String(body.message), { version: (body.version ?? 0) + 1 });
          await route.fulfill({ status: 200, json: state.current });
          return;
        }
        state.withdrawn += 1;
        state.current = null;
        await route.fulfill({ status: 204, body: '' });
      },
    },
    {
      url: '**/api/v1/agents/chat/waiting/join*',
      method: 'POST',
      handler: async route => {
        state.joins.push((route.request().postDataJSON() ?? {}) as WaitingBody);
        if (state.noteClosed || state.current === null) {
          // The loop reached its exit: the words keep waiting, and say so.
          state.joinable = false;
          if (state.current) state.current = { ...state.current, can_join: false };
          await route.fulfill({
            status: 409,
            json: {
              detail: {
                error: 'waiting_note_closed',
                message: 'LIA termine sa réponse : ton message partira juste après.',
              },
            },
          });
          return;
        }
        state.current = {
          ...state.current,
          status: 'joining',
          stream_id: 'stream-1',
          can_join: false,
        };
        await route.fulfill({ status: 200, json: state.current });
      },
    },
  ];
}

function freshState() {
  return {
    bodies: [] as ChatBody[],
    kept: [] as WaitingBody[],
    edits: [] as WaitingBody[],
    withdrawn: 0,
    current: null as ReturnType<typeof waiting> | null,
    refuse: false,
    joins: [] as WaitingBody[],
    joinable: false,
    noteClosed: false,
  };
}

test.describe('chat waiting message (ADR-384)', () => {
  test('words typed while LIA answers wait below the thread, then can be edited and withdrawn', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const state = freshState();
    await authenticate();
    await mockApi(waitingRoutes(state, gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    const composer = page.locator('textarea[data-chat-composer]');
    await composer.fill('Ajoute le dentiste');
    await composer.press('Enter');
    await expect.poll(() => state.bodies.length).toBe(1);

    // LIA is answering: the composer stays open and says where the words go.
    await expect(page.getByRole('button', { name: 'Arrêter' })).toBeVisible();
    await composer.fill('et la boulangerie');
    await page.getByRole('button', { name: 'Envoyer ensuite' }).click();

    await expect.poll(() => state.kept.length).toBe(1);
    expect(state.kept[0].message).toBe('et la boulangerie');
    expect(state.bodies).toHaveLength(1);
    const bubble = page.getByRole('group', { name: 'Message en attente' });
    await expect(bubble).toContainText('et la boulangerie');
    await expect(bubble).toContainText('Partira dès que LIA aura fini.');

    // Keyboard: edit, then save.
    await bubble.getByRole('button', { name: 'Modifier' }).focus();
    await page.keyboard.press('Enter');
    const field = bubble.getByRole('textbox', { name: 'Modifier le message en attente' });
    await expect(field).toBeFocused();
    await field.fill('et la boulangerie du marché');
    await bubble.getByRole('button', { name: 'Enregistrer' }).click();
    await expect.poll(() => state.edits.length).toBe(1);
    expect(state.edits[0]).toEqual({ message: 'et la boulangerie du marché', version: 1 });
    await expect(bubble).toContainText('et la boulangerie du marché');
    await expect(bubble.getByRole('button', { name: 'Modifier' })).toBeFocused();

    await bubble.getByRole('button', { name: 'Retirer' }).click();
    await expect.poll(() => state.withdrawn).toBe(1);
    await expect(page.getByRole('group', { name: 'Message en attente' })).toHaveCount(0);

    release();
    await expect(page.getByText('Voici le point.')).toBeVisible();
  });

  test('words the server refuses come back to the composer, with its reason', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const state = freshState();
    state.refuse = true;
    await authenticate();
    await mockApi(waitingRoutes(state, gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    const composer = page.locator('textarea[data-chat-composer]');
    await composer.fill('Première question');
    await composer.press('Enter');
    await expect.poll(() => state.bodies.length).toBe(1);

    await composer.fill('Trop tôt');
    await composer.press('Enter');
    await expect.poll(() => state.kept.length).toBe(1);
    await expect(
      page.getByText('Ton message en attente est en train de partir. Réessaie dans un instant.')
    ).toBeVisible();
    await expect(composer).toHaveValue('Trop tôt');
    await expect(page.getByRole('group', { name: 'Message en attente' })).toHaveCount(0);
    release();
  });

  test('a waiting message joins the answer in progress, read at the next step (ADR-385)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const state = freshState();
    state.joinable = true; // the answer being written takes notes
    await authenticate();
    await mockApi(waitingRoutes(state, gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    const composer = page.locator('textarea[data-chat-composer]');
    await composer.fill('Trouve des restaurants près de la gare de Lyon');
    await composer.press('Enter');
    await expect.poll(() => state.bodies.length).toBe(1);

    await composer.fill('seulement ceux ouverts le dimanche');
    await page.getByRole('button', { name: 'Envoyer ensuite' }).click();
    const bubble = page.getByRole('group', { name: 'Message en attente' });
    const join = bubble.getByRole('button', { name: 'Ajouter à la réponse en cours' });
    await expect(join).toBeVisible();

    // Keyboard equivalence: the offer is a native button.
    await join.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => state.joins.length).toBe(1);
    expect(state.joins[0]).toEqual({ version: 1 });
    await expect(bubble).toContainText('LIA le lira à sa prochaine étape');
    await expect(bubble.getByRole('button', { name: 'Envoyer maintenant' })).toHaveCount(0);
    await expect(bubble.getByRole('button', { name: 'Retirer' })).toBeVisible();

    release();
    await expect(page.getByText('Voici le point.')).toBeVisible();
  });

  test('a note the answer no longer takes keeps waiting, and says why (ADR-385)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const state = freshState();
    state.joinable = true;
    state.noteClosed = true; // the loop reaches its exit while the person clicks
    await authenticate();
    await mockApi(waitingRoutes(state, gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    const composer = page.locator('textarea[data-chat-composer]');
    await composer.fill('Trouve des restaurants près de la gare de Lyon');
    await composer.press('Enter');
    await expect.poll(() => state.bodies.length).toBe(1);
    await composer.fill('seulement ceux ouverts le dimanche');
    await page.getByRole('button', { name: 'Envoyer ensuite' }).click();

    const bubble = page.getByRole('group', { name: 'Message en attente' });
    await bubble.getByRole('button', { name: 'Ajouter à la réponse en cours' }).click();
    await expect(
      page.getByText('LIA termine sa réponse : ton message partira juste après.')
    ).toBeVisible();
    // Read again: the offer is gone, the words still wait.
    await expect(bubble.getByRole('button', { name: 'Ajouter à la réponse en cours' })).toHaveCount(
      0
    );
    await expect(bubble).toContainText('Partira dès que LIA aura fini.');
    release();
  });
});

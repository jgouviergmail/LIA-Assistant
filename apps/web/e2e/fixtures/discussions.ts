import type {
  ConversationCatalogueConfig,
  ConversationCreateRequest,
  ConversationOperationRequest,
  ConversationOperationResult,
  ConversationRenameRequest,
  ConversationSummary,
} from '../../src/types/conversation';
import type { MockRoute } from './api-mock';
import { loadedChatRoutes } from './chat';
import { appConfig } from './dashboard-shell';

export const MAIN_DISCUSSION_ID = '00000000-0000-4000-8000-00000000c001';
export const ANNEX_DISCUSSION_ID = '00000000-0000-4000-8000-00000000c002';
/**
 * What the server calls an annex created without a title, until its first
 * message names it (ADR-378 amendment 2026-11-12) — the placeholder is the
 * server's, in the person's language.
 */
export const UNTITLED_DISCUSSION = 'New discussion';

export interface DiscussionTurn {
  message: string;
  conversation_id: string;
  conversation_revision: number;
}

const date = '2026-11-09T10:00:00Z';

export function discussionFixture(
  userId: string,
  options: {
    annexTitle?: string;
    backgroundRuns?: boolean;
    creationEnabled?: boolean;
  } = {}
) {
  const main: ConversationSummary = {
    id: MAIN_DISCUSSION_ID,
    user_id: userId,
    kind: 'main',
    revision: 2,
    title: 'Conversation du 9 novembre',
    message_count: 1,
    total_tokens: 250,
    created_at: date,
    updated_at: date,
  };
  const catalogue = new Map([[main.id, main]]);
  function annex(title: string): ConversationSummary {
    return { ...main, id: ANNEX_DISCUSSION_ID, kind: 'secondary', title, revision: 0 };
  }
  if (options.annexTitle) catalogue.set(ANNEX_DISCUSSION_ID, annex(options.annexTitle));
  const rules: ConversationCatalogueConfig = {
    creation_enabled: options.creationEnabled ?? true,
    background_runs_enabled: options.backgroundRuns ?? true,
    title_max_length: 500,
    title_pattern: '^[^\\x00]*$',
    offset_max: 1000,
    page_default_limit: 20,
    page_max_limit: 50,
  };
  const turns: DiscussionTurn[] = [];
  const creates: ConversationCreateRequest[] = [];
  const renames: ConversationRenameRequest[] = [];
  const retirements: ConversationOperationRequest[] = [];
  const receipts = new Map<string, ConversationOperationResult>();
  const routes: MockRoute[] = [
    ...loadedChatRoutes(),
    { url: '**/api/v1/config', json: { ...appConfig, conversations: rules } },
    { url: '**/api/v1/conversations/me', json: main },
    {
      url: '**/api/v1/conversations?*',
      method: 'GET',
      handler: async route => {
        const offset = Number(new URL(route.request().url()).searchParams.get('offset') ?? 0);
        await route.fulfill({
          json: {
            items: Array.from(catalogue.values()).slice(offset, offset + 20),
            total_count: catalogue.size,
            offset,
            limit: 20,
          },
        });
      },
    },
    {
      url: '**/api/v1/conversations',
      method: 'POST',
      handler: async route => {
        const request = route.request().postDataJSON() as ConversationCreateRequest;
        creates.push(request);
        const row = annex(request.title ?? UNTITLED_DISCUSSION);
        catalogue.set(row.id, row);
        await route.fulfill({ json: { conversation: row, replayed: false } });
      },
    },
    {
      url: `**/api/v1/conversations/${ANNEX_DISCUSSION_ID}`,
      method: 'GET',
      handler: async route => {
        const row = catalogue.get(ANNEX_DISCUSSION_ID);
        await route.fulfill(row ? { json: row } : { status: 404, json: {} });
      },
    },
    {
      url: `**/api/v1/conversations/${ANNEX_DISCUSSION_ID}`,
      method: 'PATCH',
      handler: async route => {
        const request = route.request().postDataJSON() as ConversationRenameRequest;
        renames.push(request);
        const row = catalogue.get(ANNEX_DISCUSSION_ID);
        if (
          !row ||
          row.revision !== request.expected_revision ||
          row.title !== request.expected_title
        ) {
          await route.fulfill({
            status: 409,
            json: { detail: { error: 'conversation_title_changed' } },
          });
          return;
        }
        const updated = { ...row, title: request.title };
        catalogue.set(row.id, updated);
        await route.fulfill({ json: updated });
      },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      handler: async route => {
        const id =
          new URL(route.request().url()).searchParams.get('conversation_id') ?? MAIN_DISCUSSION_ID;
        const row = catalogue.get(id);
        const messages = row?.message_count
          ? [
              {
                id: `${id}-history`,
                role: 'assistant',
                content: id === MAIN_DISCUSSION_ID ? 'Historique principal' : 'Historique annexe',
                created_at: date,
              },
            ]
          : [];
        await route.fulfill({
          json: {
            conversation_id: id,
            messages,
            total_count: messages.length,
            has_more: false,
            next_cursor: null,
          },
        });
      },
    },
    {
      url: '**/api/v1/conversations/me/totals?*',
      handler: async route => {
        const query = new URL(route.request().url()).searchParams;
        const id = query.get('conversation_id') ?? MAIN_DISCUSSION_ID;
        const row = catalogue.get(id);
        if (!row || String(row.revision) !== query.get('conversation_revision')) {
          await route.fulfill({ status: row ? 409 : 404, json: {} });
          return;
        }
        const main = row.kind === 'main';
        const old = Number(row.message_count > 0);
        const newTurns = turns.filter(
          turn => turn.conversation_id === id && turn.conversation_revision === row.revision
        ).length;
        await route.fulfill({
          json: {
            conversation_id: id,
            conversation_revision: row.revision,
            user_message_count: old + newTurns,
            total_tokens_in: old * (main ? 80 : 30) + newTurns * 20,
            total_tokens_out: old * 5 + newTurns * 2,
            total_tokens_cache: old * (main ? 15 : 5) + newTurns * 3,
            total_google_api_requests: 0,
            total_cost_eur: old * (main ? 0.42 : 0.17) + newTurns * 0.11,
            context_tokens: old * (main ? 68000 : 12000) + newTurns * 8000,
            context_threshold: 100000,
          },
        });
      },
    },
    { url: '**/api/v1/agents/runs/active?*', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending?*', json: null },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        turns.push(route.request().postDataJSON() as DiscussionTurn);
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'data: {"type":"token","content":"Réponse dans la bonne discussion"}\n\n' +
            'data: {"type":"done","content":"","metadata":{"tokens_in":20,"tokens_out":2,"tokens_cache":3,"cost_eur":0.11}}\n\n',
        });
      },
    },
    ...(['reset', 'delete'] as const).map(
      (action): MockRoute => ({
        url: `**/api/v1/conversations/${ANNEX_DISCUSSION_ID}${action === 'reset' ? '/reset' : ''}`,
        method: action === 'reset' ? 'POST' : 'DELETE',
        handler: async route => {
          if (route.request().headers()['content-type']?.split(';', 1)[0] !== 'application/json') {
            await route.fulfill({ status: 422, json: { detail: { error_code: 'INVALID_INPUT' } } });
            return;
          }
          const request = route.request().postDataJSON() as ConversationOperationRequest;
          retirements.push(request);
          const row = catalogue.get(ANNEX_DISCUSSION_ID);
          if (!row || row.revision !== request.expected_revision) {
            await route.fulfill({
              status: 409,
              json: { detail: { error: 'conversation_changed' } },
            });
            return;
          }
          const revision = action === 'reset' ? row.revision + 1 : null;
          const receipt: ConversationOperationResult = {
            operation_id: request.operation_id,
            conversation_id: row.id,
            old_revision: row.revision,
            new_revision: revision,
            previous_message_count: row.message_count,
            logical_applied: true,
            cleanup_complete: action === 'reset',
            state: action === 'reset' ? 'succeeded' : 'needs_attention',
            replayed: false,
          };
          if (revision === null) catalogue.delete(row.id);
          else catalogue.set(row.id, { ...row, revision, message_count: 0, total_tokens: 0 });
          receipts.set(request.operation_id, receipt);
          await route.fulfill({ status: 202, json: receipt });
        },
      })
    ),
    {
      url: '**/api/v1/conversations/operations/*',
      method: 'GET',
      handler: async route => {
        const operationId = new URL(route.request().url()).pathname.split('/').at(-1) ?? '';
        const receipt = receipts.get(operationId);
        await route.fulfill(receipt ? { json: receipt } : { status: 404, json: {} });
      },
    },
    {
      url: '**/api/v1/conversations/operations/*/retry',
      method: 'POST',
      handler: async route => {
        const operationId = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
        const receipt = receipts.get(operationId);
        if (!receipt) {
          await route.fulfill({ status: 404, json: {} });
          return;
        }
        const complete: ConversationOperationResult = {
          ...receipt,
          state: 'succeeded',
          cleanup_complete: true,
        };
        receipts.set(operationId, complete);
        await route.fulfill({ status: 202, json: complete });
      },
    },
  ];
  return { routes, rules, catalogue, turns, creates, renames, retirements };
}

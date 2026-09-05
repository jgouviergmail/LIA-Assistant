/**
 * chat-reducer — streaming actions (STREAM_START / TOKEN / REPLACE / DONE /
 * ERROR).
 *
 * The STREAM_DONE fallback-to-last-assistant path and the HITL id guard are
 * covered by chat-reducer.hitl-token-guard.test.ts; the context-usage pill
 * fields by chat-reducer.context-usage.test.ts. This suite covers the
 * remaining branches: idempotent START, buffer accumulation, no-op guards,
 * full metadata mapping and totals accumulation.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import { deepFreeze } from '@/__tests__/deep-freeze';

function makeMessage(id: string, role: Message['role'] = 'assistant', content = ''): Message {
  return { id, role, content, timestamp: new Date() };
}

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

function streamingState(messageId: string, buffer: string, messages: Message[]): ChatState {
  return frozenState({
    status: 'streaming',
    streaming: {
      currentMessageId: messageId,
      streamBuffer: buffer,
      sseStatus: 'connected',
      phase: 'answer',
    },
    messages,
  });
}

describe('chatReducer — STREAM_START', () => {
  it('creates the assistant message with the initial content', () => {
    const next = chatReducer(frozenState({ status: 'sending' }), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*thinking…*' },
    });

    expect(next.status).toBe('streaming');
    expect(next.messages).toHaveLength(1);
    expect(next.messages[0]).toMatchObject({
      id: 'a-1',
      role: 'assistant',
      content: '*thinking…*',
    });
    expect(next.streaming.currentMessageId).toBe('a-1');
    expect(next.streaming.streamBuffer).toBe('*thinking…*');
  });

  it('defaults to an empty content when initialContent is omitted', () => {
    const next = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1' },
    });

    expect(next.messages[0].content).toBe('');
    expect(next.streaming.streamBuffer).toBe('');
  });

  it('is idempotent: re-targets an existing message instead of duplicating it', () => {
    // Happens when a progress message was already created (e.g. by
    // router_decision) and STREAM_START is re-dispatched for the same id.
    const existing = makeMessage('a-1', 'assistant', 'progress content');
    const state = frozenState({ status: 'sending', messages: [existing] });

    const next = chatReducer(state, {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: 'ignored' },
    });

    expect(next.messages).toHaveLength(1);
    expect(next.messages[0]).toBe(existing);
    expect(next.status).toBe('streaming');
    expect(next.streaming.currentMessageId).toBe('a-1');
    // Buffer resyncs to the existing content so STREAM_TOKEN appends correctly.
    expect(next.streaming.streamBuffer).toBe('progress content');
  });
});

describe('chatReducer — STREAM_TOKEN', () => {
  it('appends the token to the target message and the buffer', () => {
    const state = streamingState('a-1', 'Hello', [makeMessage('a-1', 'assistant', 'Hello')]);

    const next = chatReducer(state, { type: 'STREAM_TOKEN', payload: { token: ' world' } });

    expect(next.messages[0].content).toBe('Hello world');
    expect(next.streaming.streamBuffer).toBe('Hello world');
  });

  it('ignores tokens when no stream is active (same state reference)', () => {
    const state = frozenState();

    const next = chatReducer(state, { type: 'STREAM_TOKEN', payload: { token: 'late' } });

    expect(next).toBe(state);
  });

  it('ignores tokens when the target message vanished (state inconsistency guard)', () => {
    const state = streamingState('ghost', 'buf', [makeMessage('other', 'assistant')]);

    const next = chatReducer(state, { type: 'STREAM_TOKEN', payload: { token: 'x' } });

    expect(next).toBe(state);
  });
});

describe('chatReducer — STREAM_REPLACE', () => {
  it('replaces the message content entirely and resets the buffer to it', () => {
    const state = streamingState('a-1', 'old buffer', [
      makeMessage('a-1', 'assistant', 'placeholder'),
    ]);

    const next = chatReducer(state, {
      type: 'STREAM_REPLACE',
      payload: { content: 'final answer' },
    });

    expect(next.messages[0].content).toBe('final answer');
    expect(next.streaming.streamBuffer).toBe('final answer');
  });

  it('is a no-op without an active stream', () => {
    const state = frozenState();

    const next = chatReducer(state, { type: 'STREAM_REPLACE', payload: { content: 'x' } });

    expect(next).toBe(state);
  });

  it('is a no-op when the target message is missing', () => {
    const state = streamingState('ghost', '', [makeMessage('other', 'assistant')]);

    const next = chatReducer(state, { type: 'STREAM_REPLACE', payload: { content: 'x' } });

    expect(next).toBe(state);
  });
});

describe('chatReducer — STREAM_DONE', () => {
  const fullMetadata = {
    tokens_in: 100,
    tokens_out: 50,
    tokens_cache: 25,
    cost_eur: 0.02,
    message_count: 2,
    google_api_requests: 3,
    tts_provider: 'elevenlabs',
    tts_model: 'eleven_v3',
    tts_characters: 420,
    tts_cost_eur: 0.01,
    skill_name: 'weather',
    generated_images: [{ url: 'https://img/1.png', alt: 'img' }],
    generated_documents: [
      {
        url: '/api/v1/attachments/d1',
        filename: 'modeles-llm.csv',
        doc_type: 'csv',
        size_bytes: 2048,
        expires_at: null,
      },
    ],
    browser_screenshot: { url: 'https://shot/1.jpg', alt: 'shot' },
    psyche_state: {
      mood_label: 'joyful',
      mood_color: '#00ff00',
      mood_pleasure: 0.8,
      mood_arousal: 0.4,
      mood_dominance: 0.5,
      active_emotion: 'joy',
      emotion_intensity: 0.7,
      relationship_stage: 'EXPLORATION',
    },
  };

  it('maps the full done metadata onto the matching message', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: fullMetadata },
    });

    expect(next.messages[0]).toMatchObject({
      tokensIn: 100,
      tokensOut: 50,
      tokensCache: 25,
      costEur: 0.02,
      googleApiRequests: 3,
      ttsProvider: 'elevenlabs',
      ttsModel: 'eleven_v3',
      ttsCharacters: 420,
      ttsCostEur: 0.01,
      skillName: 'weather',
      generatedImages: [{ url: 'https://img/1.png', alt: 'img' }],
      generatedDocuments: [
        {
          url: '/api/v1/attachments/d1',
          filename: 'modeles-llm.csv',
          doc_type: 'csv',
          size_bytes: 2048,
          expires_at: null,
        },
      ],
      browserScreenshot: { url: 'https://shot/1.jpg', alt: 'shot' },
    });
    expect(next.messages[0].metadata?.psyche_state).toEqual(fullMetadata.psyche_state);
    // A NORMAL done never marks the bubble as interrupted (ADR-117 Lot 3)
    expect(next.messages[0].metadata?.interrupted).toBeUndefined();
    // No archived id in the metadata → no feedback target on the live bubble
    expect(next.messages[0].metadata?.message_db_id).toBeUndefined();
  });

  it('carries the archived DB id onto the live bubble (QW-5, ADR-138)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'a-1',
        metadata: { ...fullMetadata, archived_message_id: 'db-uuid-1' },
      },
    });

    // The feedback buttons target the archived row through this id.
    expect(next.messages[0].metadata?.message_db_id).toBe('db-uuid-1');
    // No chips in this done → the field never appears on the bubble.
    expect(next.messages[0].metadata?.followup_suggestions).toBeUndefined();
  });

  it('carries the follow-up chips onto the live bubble (UXR Lot 4, A2)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'a-1',
        metadata: {
          ...fullMetadata,
          followup_suggestions: ['Montre la météo de demain', 'Ajoute un rappel'],
        },
      },
    });

    // Same field name as the archived message_metadata — live and reloaded
    // rows read identically.
    expect(next.messages[0].metadata?.followup_suggestions).toEqual([
      'Montre la météo de demain',
      'Ajoute un rappel',
    ]);
  });

  it('carries what the turn PERFORMED onto the live bubble (ADR-263)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'a-1',
        metadata: {
          ...fullMetadata,
          performed_effects: [
            {
              label_key: 'effects.labels.draft.email',
              values: { recipient: 'Marie' },
              status: 'succeeded',
              tool_name: 'draft:email',
            },
          ],
        },
      },
    });

    // Same key the archived row uses, so a reload hydrates the same shape...
    expect(next.messages[0].metadata?.performed_effects).toHaveLength(1);
    // ...and the typed field is parsed by the ONE parser the history path uses.
    expect(next.messages[0].performedEffects).toEqual([
      {
        labelKey: 'effects.labels.draft.email',
        values: { recipient: 'Marie' },
        status: 'succeeded',
        toolName: 'draft:email',
      },
    ]);
  });

  it('writes no effect field for a turn that changed nothing (ADR-263)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: { ...fullMetadata, performed_effects: [] } },
    });

    expect(next.messages[0].metadata?.performed_effects).toBeUndefined();
    expect(next.messages[0].performedEffects).toBeUndefined();
  });

  it('drops an EMPTY chips list instead of writing a hollow field (UXR A2)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'a-1',
        metadata: { ...fullMetadata, followup_suggestions: [] },
      },
    });

    expect(next.messages[0].metadata?.followup_suggestions).toBeUndefined();
  });

  it('carries the initiative motivation onto the live bubble (Lot 1-A3)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'a-1',
        metadata: {
          ...fullMetadata,
          followup_suggestions: ['Montre le calendrier F1'],
          initiative_motivation: 'Parce que tu suis la Formule 1',
        },
      },
    });

    expect(next.messages[0].metadata?.initiative_motivation).toBe('Parce que tu suis la Formule 1');
  });

  it('drops an absent motivation instead of writing a hollow field (Lot 1-A3)', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: { ...fullMetadata } },
    });

    expect(next.messages[0].metadata?.initiative_motivation).toBeUndefined();
  });

  it('flags the partial bubble as interrupted on a cancelled done (ADR-117 Lot 3)', () => {
    const state = streamingState('a-1', 'partial', [makeMessage('a-1', 'assistant', 'partial')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: { cancelled: true } },
    });

    // Same flag as archived history rows — one badge for live and reload
    expect(next.messages[0].metadata).toMatchObject({
      interrupted: true,
      interrupt_reason: 'cancelled',
    });
    // The partial content is KEPT (product decision: never silently dropped)
    expect(next.messages[0].content).toBe('partial');
  });

  it('flags interrupted through the last-assistant fallback too (ADR-117 Lot 3)', () => {
    // done targets an unknown id -> fallback attaches to the last assistant
    const state = streamingState('gone-id', 'partial', [
      makeMessage('a-9', 'assistant', 'partial'),
    ]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'gone-id', metadata: { cancelled: true } },
    });

    expect(next.messages[0].metadata).toMatchObject({
      interrupted: true,
      interrupt_reason: 'cancelled',
    });
  });

  it('leaves non-matching messages untouched when metadata targets one message', () => {
    const bystander = makeMessage('u-1', 'user', 'question');
    const target = makeMessage('a-1', 'assistant', 'answer');
    const state = streamingState('a-1', 'answer', [bystander, target]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: { tokens_in: 7 } },
    });

    expect(next.messages[0]).toBe(bystander);
    expect(next.messages[1].tokensIn).toBe(7);
  });

  it('fallback path: attaches full metadata to the last assistant message among several', () => {
    // No message matches the done messageId → the reducer walks back to the
    // last assistant message and enriches it, leaving earlier messages as-is.
    const earlier = makeMessage('a-0', 'assistant', 'older answer');
    const user = makeMessage('u-1', 'user', 'question');
    const last = makeMessage('a-1', 'assistant', 'latest answer');
    const state = streamingState('ghost', '', [earlier, user, last]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'ghost', metadata: fullMetadata },
    });

    expect(next.messages[0]).toBe(earlier);
    expect(next.messages[1]).toBe(user);
    expect(next.messages[2]).toMatchObject({
      tokensIn: 100,
      ttsProvider: 'elevenlabs',
      skillName: 'weather',
    });
    expect(next.messages[2].metadata?.psyche_state).toEqual(fullMetadata.psyche_state);
  });

  it('nullifies absent TTS attribution fields (free providers stay badge-less)', () => {
    const state = streamingState('a-1', '', [makeMessage('a-1')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: { tokens_in: 1 } },
    });

    expect(next.messages[0].ttsProvider).toBeNull();
    expect(next.messages[0].ttsModel).toBeNull();
    expect(next.messages[0].ttsCharacters).toBeNull();
    expect(next.messages[0].ttsCostEur).toBeNull();
  });

  it('accumulates conversation totals across turns', () => {
    const state = streamingState('a-1', '', [makeMessage('a-1')]);

    const first = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: fullMetadata },
    });
    const secondState = deepFreeze({
      ...first,
      status: 'streaming' as const,
      streaming: {
        currentMessageId: 'a-1',
        streamBuffer: '',
        sseStatus: 'connected' as const,
        phase: 'answer' as const,
      },
    });
    const second = chatReducer(secondState, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: fullMetadata },
    });

    expect(second.totals).toEqual({
      totalTokensIn: 200,
      totalTokensOut: 100,
      totalTokensCache: 50,
      totalCostEur: 0.04,
      totalMessages: 4,
      totalGoogleApiRequests: 6,
    });
  });

  it('treats missing numeric metadata fields as zero in the totals', () => {
    const state = streamingState('a-1', '', [makeMessage('a-1')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1', metadata: {} },
    });

    expect(next.totals).toEqual(initialChatState.totals);
  });

  it('finalizes the stream: idle status, streaming reset, screenshot cleared', () => {
    const state = frozenState({
      status: 'streaming',
      streaming: {
        currentMessageId: 'a-1',
        streamBuffer: 'x',
        sseStatus: 'connected',
        phase: 'answer',
      },
      messages: [makeMessage('a-1')],
      browserScreenshot: { image_base64: 'b64', url: 'https://x', title: 't' },
    });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1' },
    });

    expect(next.status).toBe('idle');
    expect(next.streaming).toEqual({
      currentMessageId: null,
      streamBuffer: '',
      sseStatus: 'disconnected',
      phase: 'answer',
    });
    expect(next.browserScreenshot).toBeNull();
  });

  it('leaves messages and totals untouched when metadata is absent', () => {
    const state = streamingState('a-1', 'answer', [makeMessage('a-1', 'assistant', 'answer')]);

    const next = chatReducer(state, { type: 'STREAM_DONE', payload: { messageId: 'a-1' } });

    expect(next.messages).toBe(state.messages);
    expect(next.totals).toBe(state.totals);
  });

  it('leaves messages untouched when no message matches and none is an assistant message', () => {
    const state = streamingState('ghost', '', [makeMessage('u-1', 'user', 'hi')]);

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'ghost', metadata: { tokens_in: 5 } },
    });

    expect(next.messages).toEqual(state.messages);
    // Totals still accumulate: the turn did consume tokens.
    expect(next.totals.totalTokensIn).toBe(5);
  });
});

describe('chatReducer — STREAM_ERROR', () => {
  it('appends the backend-localized error as an assistant bubble and flags the error state', () => {
    const state = streamingState('a-1', 'partial', [makeMessage('a-1', 'assistant', 'partial')]);

    const next = chatReducer(state, {
      type: 'STREAM_ERROR',
      payload: { error: 'Something went wrong (localized)' },
    });

    expect(next.status).toBe('error');
    expect(next.streaming.sseStatus).toBe('error');
    expect(next.messages).toHaveLength(2);
    expect(next.messages[1].role).toBe('assistant');
    expect(next.messages[1].content).toBe('Something went wrong (localized)');
  });
});

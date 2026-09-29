import { describe, expect, it } from 'vitest';
import { processSSEChunk } from '..';
import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState } from '@/types/chat-state';
import type { QualifiedCollection } from '@/types/result-preview';
import { buildHandlerContext } from './context-fixture';

const collection: QualifiedCollection = {
  kind: 'EMAIL',
  candidate_count: 2,
  evaluated_count: 2,
  omitted_count: 0,
  items: [
    { id: 'email_1', title: 'Contract', excerpt: 'Reply today', verdict: 'match' },
    { id: 'email_2', title: 'Other', excerpt: 'Unrelated', verdict: 'non_match' },
  ],
};

describe('qualified collection stream', () => {
  it('validates and forwards an early preview without inventing answer text', () => {
    const { context, dispatch } = buildHandlerContext();
    processSSEChunk({ type: 'result_preview', content: '', metadata: { collection } }, context);
    expect(dispatch).toHaveBeenCalledExactlyOnceWith({
      type: 'RESULT_PREVIEW',
      payload: { messageId: 'assistant-1', collection },
    });
  });

  it.each(['REMINDER', 'TICKET', 'MCP_RESULT', 'NOTE'] as const)(
    'delivers %s without losing other domains',
    kind => {
      const { context, dispatch } = buildHandlerContext();
      const incoming = { ...collection, kind };
      processSSEChunk(
        { type: 'result_preview', content: '', metadata: { collection: incoming } },
        context
      );
      expect(dispatch).toHaveBeenCalledExactlyOnceWith({
        type: 'RESULT_PREVIEW',
        payload: { messageId: 'assistant-1', collection: incoming },
      });
    }
  );

  it('uses the active progress message when the answer has not started', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'progress-1' });
    processSSEChunk({ type: 'result_preview', content: '', metadata: { collection } }, context);
    expect(dispatch).toHaveBeenCalledExactlyOnceWith({
      type: 'RESULT_PREVIEW',
      payload: { messageId: 'progress-1', collection },
    });
  });

  it.each([undefined, {}])('ignores an event without a collection: %s', metadata => {
    const { context, dispatch } = buildHandlerContext();
    processSSEChunk({ type: 'result_preview', content: '', metadata }, context);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('replaces a collection update while keeping independently arriving domains', () => {
    let state = chatReducer(initialChatState, {
      type: 'STREAM_START',
      payload: { messageId: 'current' },
    });
    const events: QualifiedCollection = { ...collection, kind: 'EVENT' };
    const updated: QualifiedCollection = { ...collection, items: [...collection.items].reverse() };
    for (const next of [collection, events, updated]) {
      state = chatReducer(state, {
        type: 'RESULT_PREVIEW',
        payload: { messageId: 'current', collection: next },
      });
    }
    expect(state.resultPreviews).toEqual([events, updated]);
    const done = chatReducer(state, { type: 'STREAM_DONE', payload: { messageId: 'current' } });
    expect(
      chatReducer(done, { type: 'RESULT_PREVIEW', payload: { messageId: 'current', collection } })
    ).toBe(done);
  });

  it.each([
    { ...collection, kind: 'DRAFT' },
    { ...collection, items: [...collection.items, collection.items[0]] },
    { ...collection, candidate_count: 1 },
    { ...collection, evaluated_count: -1 },
    { ...collection, items: [{ ...collection.items[0], verdict: 'delete' }] },
  ])('drops invalid or inconsistent data', invalid => {
    const { context, dispatch } = buildHandlerContext();
    processSSEChunk(
      { type: 'result_preview', content: '', metadata: { collection: invalid } },
      context
    );
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('rejects a late previous response and clears previews on termination', () => {
    const streaming = chatReducer(initialChatState, {
      type: 'STREAM_START',
      payload: { messageId: 'current' },
    });
    const preview = chatReducer(streaming, {
      type: 'RESULT_PREVIEW',
      payload: { messageId: 'current', collection },
    });
    expect(preview.resultPreviews).toHaveLength(1);
    expect(
      chatReducer(preview, { type: 'RESULT_PREVIEW', payload: { messageId: 'old', collection } })
    ).toBe(preview);
    for (const action of ['CLEAR_MESSAGES', 'SSE_DISCONNECTED', 'SSE_CONNECTING'] as const) {
      expect(chatReducer(preview, { type: action }).resultPreviews).toEqual([]);
    }
    expect(
      chatReducer(preview, { type: 'STREAM_DONE', payload: { messageId: 'current' } })
        .resultPreviews
    ).toEqual([]);
    expect(
      chatReducer(preview, { type: 'SSE_ERROR', payload: { error: 'failed' } }).resultPreviews
    ).toEqual([]);
  });
});

/**
 * sse-handlers — side-channel data events: LARS registry updates and debug
 * panel metrics (initial + supplementary merge).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import {
  handleRegistryUpdate,
  handleDebugMetrics,
  handleDebugMetricsUpdate,
} from '@/lib/sse-handlers/handlers';
import { logger } from '@/lib/logger';
import type { ChatStreamChunk } from '@/types/chat';
import { buildHandlerContext, dispatchedOfType } from './context-fixture';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('handleRegistryUpdate', () => {
  it('dispatches REGISTRY_UPDATE with the received items', () => {
    const { context, dispatch } = buildHandlerContext();
    const items = {
      contact_1: { id: 'contact_1', type: 'contact', payload: { name: 'Alice' }, meta: {} },
    };

    handleRegistryUpdate(
      { type: 'registry_update', content: '', metadata: { items, count: 1 } } as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'REGISTRY_UPDATE')).toEqual([{ items }]);
  });

  it('derives the item count for logging when the metadata omits `count`', () => {
    const { context, dispatch } = buildHandlerContext();
    const items = {
      email_1: { id: 'email_1', type: 'email', payload: {}, meta: {} },
      email_2: { id: 'email_2', type: 'email', payload: {}, meta: {} },
    };

    handleRegistryUpdate(
      { type: 'registry_update', content: '', metadata: { items } } as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'REGISTRY_UPDATE')).toEqual([{ items }]);
    expect(logger.debug).toHaveBeenCalledWith(
      'chat_registry_update',
      expect.objectContaining({ item_count: 2 })
    );
  });

  it('warns and dispatches nothing when items are missing or malformed', () => {
    const { context, dispatch } = buildHandlerContext();

    handleRegistryUpdate(
      {
        type: 'registry_update',
        content: '',
        metadata: { items: 'not-an-object' },
      } as ChatStreamChunk,
      context
    );
    handleRegistryUpdate(
      { type: 'registry_update', content: '', metadata: undefined } as ChatStreamChunk,
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
    expect(logger.warn).toHaveBeenCalledTimes(2);
    expect(vi.mocked(logger.warn).mock.calls[0][0]).toBe('chat_registry_update_invalid');
  });
});

describe('handleDebugMetrics', () => {
  const metrics = {
    query_info: { original_query: 'what is the weather?' },
    routing_decision: { route_to: 'weather_agent' },
  };

  it('sets current metrics AND appends a history entry with the original query', () => {
    const { context, dispatch } = buildHandlerContext();

    handleDebugMetrics(
      { type: 'debug_metrics', content: '', metadata: metrics } as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'DEBUG_METRICS_SET')).toEqual([{ metrics }]);
    const historyPayloads = dispatchedOfType(dispatch, 'DEBUG_METRICS_ADD_TO_HISTORY') as Array<{
      entry: { id: string; query: string; timestamp: Date };
    }>;
    expect(historyPayloads).toHaveLength(1);
    expect(historyPayloads[0].entry.query).toBe('what is the weather?');
    expect(historyPayloads[0].entry.id).toBeTruthy();
    expect(historyPayloads[0].entry.timestamp).toBeInstanceOf(Date);
  });

  it('labels the history entry "Unknown query" when query_info is absent', () => {
    const { context, dispatch } = buildHandlerContext();

    handleDebugMetrics(
      { type: 'debug_metrics', content: '', metadata: { routing_decision: {} } } as ChatStreamChunk,
      context
    );

    const historyPayloads = dispatchedOfType(dispatch, 'DEBUG_METRICS_ADD_TO_HISTORY') as Array<{
      entry: { query: string };
    }>;
    expect(historyPayloads[0].entry.query).toBe('Unknown query');
  });

  it('dispatches nothing when the metadata payload is absent', () => {
    const { context, dispatch } = buildHandlerContext();

    handleDebugMetrics(
      { type: 'debug_metrics', content: '', metadata: undefined } as ChatStreamChunk,
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
  });
});

describe('handleDebugMetricsUpdate', () => {
  it('dispatches the supplementary metrics merge', () => {
    const { context, dispatch } = buildHandlerContext();
    const update = { journal_extraction: { entries: 3 } };

    handleDebugMetricsUpdate(
      { type: 'debug_metrics_update', content: '', metadata: update } as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'DEBUG_METRICS_UPDATE')).toEqual([{ metrics: update }]);
  });

  it('dispatches nothing without a payload', () => {
    const { context, dispatch } = buildHandlerContext();

    handleDebugMetricsUpdate(
      { type: 'debug_metrics_update', content: '', metadata: undefined } as ChatStreamChunk,
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
  });
});

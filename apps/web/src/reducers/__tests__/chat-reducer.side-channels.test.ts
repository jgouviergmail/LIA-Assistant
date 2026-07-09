/**
 * chat-reducer — side-channel actions: LARS registry, debug panel metrics,
 * browser screenshots, HITL approval messages, router decision no-op and the
 * exhaustiveness fallback.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import {
  initialChatState,
  type ChatAction,
  type ChatState,
  type DebugMetricsEntry,
} from '@/types/chat-state';
import type { DebugMetrics, Message, RegistryItem } from '@/types/chat';
import { deepFreeze } from '@/__tests__/deep-freeze';

function makeMessage(id: string, role: Message['role'] = 'assistant'): Message {
  return { id, role, content: `content-${id}`, timestamp: new Date() };
}

function makeRegistryItem(id: string, payload: Record<string, unknown> = {}): RegistryItem {
  return {
    id,
    type: 'CONTACT',
    payload,
    meta: { source: 'google_contacts', timestamp: '2026-07-09T00:00:00Z' },
  };
}

function makeMetrics(query = 'q'): DebugMetrics {
  // The reducer treats DebugMetrics as an opaque payload — a minimal cast
  // fixture keeps the test independent from the (large) debug panel schema.
  return { query_info: { original_query: query } } as unknown as DebugMetrics;
}

function makeHistoryEntry(id: string): DebugMetricsEntry {
  return { id, timestamp: new Date(), query: `query-${id}`, metrics: makeMetrics(id) };
}

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

describe('chatReducer — ROUTER_DECISION', () => {
  it('is informational only (same state reference)', () => {
    const state = frozenState();

    const next = chatReducer(state, {
      type: 'ROUTER_DECISION',
      payload: {
        intention: 'conversation',
        confidence: 0.97,
        context_label: 'chitchat',
        next_node: 'response',
      },
    });

    expect(next).toBe(state);
  });
});

describe('chatReducer — HITL approval messages', () => {
  it('ADD_APPROVAL_MESSAGE appends the approval bubble', () => {
    const state = frozenState({ messages: [makeMessage('u-1', 'user')] });
    const approval = makeMessage('hitl_1');

    const next = chatReducer(state, {
      type: 'ADD_APPROVAL_MESSAGE',
      payload: { message: approval },
    });

    expect(next.messages).toHaveLength(2);
    expect(next.messages[1]).toBe(approval);
  });

  it('REMOVE_APPROVAL_MESSAGE removes it by id and ignores unknown ids', () => {
    const keep = makeMessage('a-1');
    const state = frozenState({ messages: [keep, makeMessage('hitl_1')] });

    const removed = chatReducer(state, {
      type: 'REMOVE_APPROVAL_MESSAGE',
      payload: { messageId: 'hitl_1' },
    });
    expect(removed.messages).toEqual([keep]);

    const untouched = chatReducer(deepFreeze(removed), {
      type: 'REMOVE_APPROVAL_MESSAGE',
      payload: { messageId: 'does-not-exist' },
    });
    expect(untouched.messages).toEqual([keep]);
  });
});

describe('chatReducer — LARS registry', () => {
  it('REGISTRY_UPDATE merges items into the registry', () => {
    const existing = makeRegistryItem('contact_1', { name: 'Alice' });
    const state = frozenState({ registry: { contact_1: existing } });
    const incoming = {
      email_1: makeRegistryItem('email_1', { subject: 'Hello' }),
    };

    const next = chatReducer(state, { type: 'REGISTRY_UPDATE', payload: { items: incoming } });

    expect(next.registry).toEqual({ contact_1: existing, email_1: incoming.email_1 });
  });

  it('REGISTRY_UPDATE is last-write-wins for an existing id', () => {
    const state = frozenState({
      registry: { contact_1: makeRegistryItem('contact_1', { name: 'Alice' }) },
    });
    const updated = makeRegistryItem('contact_1', { name: 'Alice Updated' });

    const next = chatReducer(state, {
      type: 'REGISTRY_UPDATE',
      payload: { items: { contact_1: updated } },
    });

    expect(next.registry.contact_1).toBe(updated);
    expect(Object.keys(next.registry)).toHaveLength(1);
  });

  it('REGISTRY_CLEAR empties the registry', () => {
    const state = frozenState({
      registry: { contact_1: makeRegistryItem('contact_1') },
    });

    const next = chatReducer(state, { type: 'REGISTRY_CLEAR' });

    expect(next.registry).toEqual({});
  });
});

describe('chatReducer — debug panel metrics', () => {
  it('DEBUG_METRICS_SET stores the current request metrics', () => {
    const metrics = makeMetrics();

    const next = chatReducer(frozenState(), {
      type: 'DEBUG_METRICS_SET',
      payload: { metrics },
    });

    expect(next.currentDebugMetrics).toBe(metrics);
  });

  it('DEBUG_METRICS_ADD_TO_HISTORY prepends (most recent first)', () => {
    const older = makeHistoryEntry('older');
    const state = frozenState({ debugMetricsHistory: [older] });
    const newer = makeHistoryEntry('newer');

    const next = chatReducer(state, {
      type: 'DEBUG_METRICS_ADD_TO_HISTORY',
      payload: { entry: newer },
    });

    expect(next.debugMetricsHistory.map(e => e.id)).toEqual(['newer', 'older']);
  });

  it('DEBUG_METRICS_ADD_TO_HISTORY caps the history at 20 entries', () => {
    const full = Array.from({ length: 20 }, (_, i) => makeHistoryEntry(`e-${i}`));
    const state = frozenState({ debugMetricsHistory: full });

    const next = chatReducer(state, {
      type: 'DEBUG_METRICS_ADD_TO_HISTORY',
      payload: { entry: makeHistoryEntry('overflow') },
    });

    expect(next.debugMetricsHistory).toHaveLength(20);
    expect(next.debugMetricsHistory[0].id).toBe('overflow');
    expect(next.debugMetricsHistory[19].id).toBe('e-18'); // e-19 dropped
  });

  it('DEBUG_METRICS_UPDATE merges into current metrics and the latest history entry', () => {
    const state = frozenState({
      currentDebugMetrics: makeMetrics('original'),
      debugMetricsHistory: [makeHistoryEntry('latest'), makeHistoryEntry('previous')],
    });
    const update = { journal_extraction: { entries: 2 } } as unknown as Partial<DebugMetrics>;

    const next = chatReducer(state, { type: 'DEBUG_METRICS_UPDATE', payload: { metrics: update } });

    expect(next.currentDebugMetrics).toMatchObject(update);
    expect(next.debugMetricsHistory[0].metrics).toMatchObject(update);
    // Only the LATEST history entry is enriched.
    expect(next.debugMetricsHistory[1].metrics).not.toMatchObject(update);
  });

  it('DEBUG_METRICS_UPDATE keeps current=null when nothing is being tracked', () => {
    const state = frozenState({ currentDebugMetrics: null, debugMetricsHistory: [] });

    const next = chatReducer(state, {
      type: 'DEBUG_METRICS_UPDATE',
      payload: { metrics: {} as Partial<DebugMetrics> },
    });

    expect(next.currentDebugMetrics).toBeNull();
    expect(next.debugMetricsHistory).toEqual([]);
  });

  it('DEBUG_METRICS_CLEAR wipes current metrics and history', () => {
    const state = frozenState({
      currentDebugMetrics: makeMetrics(),
      debugMetricsHistory: [makeHistoryEntry('e-1')],
    });

    const next = chatReducer(state, { type: 'DEBUG_METRICS_CLEAR' });

    expect(next.currentDebugMetrics).toBeNull();
    expect(next.debugMetricsHistory).toEqual([]);
  });
});

describe('chatReducer — browser screenshots', () => {
  it('BROWSER_SCREENSHOT stores the overlay payload', () => {
    const payload = { image_base64: 'b64', url: 'https://example.com', title: 'Example' };

    const next = chatReducer(frozenState(), { type: 'BROWSER_SCREENSHOT', payload });

    expect(next.browserScreenshot).toBe(payload);
  });

  it('BROWSER_SCREENSHOT_CLEAR resets the overlay', () => {
    const state = frozenState({
      browserScreenshot: { image_base64: 'b64', url: 'https://x', title: 't' },
    });

    const next = chatReducer(state, { type: 'BROWSER_SCREENSHOT_CLEAR' });

    expect(next.browserScreenshot).toBeNull();
  });
});

describe('chatReducer — exhaustiveness fallback', () => {
  it('returns the same state for an unknown action type', () => {
    const state = frozenState();

    const next = chatReducer(state, { type: 'UNKNOWN_FUTURE_ACTION' } as unknown as ChatAction);

    expect(next).toBe(state);
  });
});

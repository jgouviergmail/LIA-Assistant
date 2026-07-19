/**
 * chat-reducer — connector error notices (Lot 3 P3, ADR-134).
 *
 * ADD dedupes by (connectorType, action) — the backend emits once per failed
 * step, so two failing email steps must yield ONE banner. DISMISS removes a
 * single banner. SEND_MESSAGE clears all notices (a new turn gets a fresh
 * verdict). Input states are deep-frozen to prove immutability.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState, type ConnectorNotice } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import { deepFreeze } from '@/__tests__/deep-freeze';

function notice(overrides: Partial<ConnectorNotice> = {}): ConnectorNotice {
  return {
    connectorType: 'google_gmail',
    action: 'reconnect',
    toolName: 'search_emails_tool',
    ...overrides,
  };
}

function frozenState(notices: ConnectorNotice[] = []): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), connectorNotices: notices });
}

function userMessage(): Message {
  return { id: 'u-1', role: 'user', content: 'hi', timestamp: new Date() };
}

describe('chatReducer — CONNECTOR_NOTICE_ADD', () => {
  it('adds a notice to an empty list', () => {
    const next = chatReducer(frozenState(), {
      type: 'CONNECTOR_NOTICE_ADD',
      payload: { notice: notice() },
    });

    expect(next.connectorNotices).toHaveLength(1);
    expect(next.connectorNotices[0].connectorType).toBe('google_gmail');
  });

  it('dedupes by (connectorType, action) — same failure twice = one banner', () => {
    const state = frozenState([notice()]);

    const next = chatReducer(state, {
      type: 'CONNECTOR_NOTICE_ADD',
      payload: { notice: notice({ toolName: 'get_emails_tool' }) },
    });

    expect(next.connectorNotices).toHaveLength(1);
    // Unchanged reference on dedup (no useless re-render).
    expect(next.connectorNotices).toBe(state.connectorNotices);
  });

  it('keeps distinct connectors and actions as separate banners', () => {
    let state: ChatState = frozenState([notice()]);

    state = chatReducer(state, {
      type: 'CONNECTOR_NOTICE_ADD',
      payload: { notice: notice({ connectorType: 'google_calendar' }) },
    });
    state = chatReducer(deepFreeze(state), {
      type: 'CONNECTOR_NOTICE_ADD',
      payload: { notice: notice({ action: 'rate_limit' }) },
    });

    expect(state.connectorNotices).toHaveLength(3);
  });
});

describe('chatReducer — CONNECTOR_NOTICE_DISMISS', () => {
  it('removes only the targeted banner', () => {
    const state = frozenState([notice(), notice({ connectorType: 'google_calendar' })]);

    const next = chatReducer(state, {
      type: 'CONNECTOR_NOTICE_DISMISS',
      payload: { connectorType: 'google_gmail', action: 'reconnect' },
    });

    expect(next.connectorNotices).toHaveLength(1);
    expect(next.connectorNotices[0].connectorType).toBe('google_calendar');
  });
});

describe('chatReducer — notices lifecycle on SEND_MESSAGE', () => {
  it('clears all notices when a new message is sent', () => {
    const state = frozenState([notice(), notice({ action: 'rate_limit' })]);

    const next = chatReducer(state, {
      type: 'SEND_MESSAGE',
      payload: { message: userMessage() },
    });

    expect(next.connectorNotices).toHaveLength(0);
  });
});

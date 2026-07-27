/**
 * Connector notice condensation (S4).
 *
 * One expired Google refresh token invalidates Gmail, Calendar and Drive at
 * once, so a single failure can stack three amber rows — ~120 px of the band
 * between the thread and the composer, on a surface S0 measured as already
 * tight.
 *
 * They condense into one line ONLY when they say the same thing. Notices with
 * different actions ("reconnect" vs "rate limited") cannot be summarised
 * without asserting something false about at least one of them, so those stay
 * listed in full — a rarer case, and the honest one.
 */

import { describe, it, expect } from 'vitest';

import { summarizeNotices } from '../connector-notice-summary';
import type { ConnectorNotice } from '@/types/chat-state';

const reconnect = (connectorType: string): ConnectorNotice => ({
  connectorType,
  action: 'reconnect',
  toolName: 'search_emails_tool',
});

const rateLimited = (connectorType: string): ConnectorNotice => ({
  connectorType,
  action: 'rate_limit',
  toolName: 'search_emails_tool',
});

describe('summarizeNotices', () => {
  it('does not condense an empty list', () => {
    expect(summarizeNotices([])).toBeNull();
  });

  it('does not condense a single notice — it already says exactly what happened', () => {
    expect(summarizeNotices([reconnect('gmail')])).toBeNull();
  });

  it('condenses several notices that share one action', () => {
    const summary = summarizeNotices([
      reconnect('gmail'),
      reconnect('google_calendar'),
      reconnect('google_drive'),
    ]);
    expect(summary).toEqual({ action: 'reconnect', count: 3 });
  });

  it('condenses rate limits the same way', () => {
    const summary = summarizeNotices([rateLimited('gmail'), rateLimited('google_calendar')]);
    expect(summary).toEqual({ action: 'rate_limit', count: 2 });
  });

  it('refuses to condense mixed actions — a summary would be false for one of them', () => {
    expect(summarizeNotices([reconnect('gmail'), rateLimited('google_calendar')])).toBeNull();
  });

  it('counts the notices, not the connectors', () => {
    // Same connector, two distinct actions: still mixed, still not condensable.
    expect(summarizeNotices([reconnect('gmail'), rateLimited('gmail')])).toBeNull();
  });

  it('is pure — it never mutates the input', () => {
    const notices = [reconnect('gmail'), reconnect('google_drive')];
    const snapshot = JSON.stringify(notices);
    summarizeNotices(notices);
    expect(JSON.stringify(notices)).toBe(snapshot);
  });
});

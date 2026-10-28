import { expect, it } from 'vitest';
import { dashboardEntry } from '../activity-entry';
it('keeps typed navigation payloads in the native bounded activity entry', () => {
  const filters = { assignee: 'lia' as const, sort: 'due' as const, overdue: true };
  expect(dashboardEntry({ kind: 'workboard', filters, ticketId: 'ticket' })).toEqual({
    selection: 'world-workboard',
    workboardFilters: filters,
    ticketId: 'ticket',
  });
  expect(dashboardEntry({ kind: 'draft', draft: 'Hello Alice' })).toEqual({
    selection: 'lia',
    draft: 'Hello Alice',
  });
  expect(dashboardEntry({ kind: 'meeting', id: 'meeting' })).toEqual({
    selection: 'world-meetings',
    meetingId: 'meeting',
  });
  expect(dashboardEntry({ kind: 'gallery', tab: 'documents' })).toEqual({
    selection: 'generated-assets',
    tab: 'documents',
  });
  expect(dashboardEntry({ kind: 'sms', messageId: 'message' })).toEqual({
    selection: 'world-sms',
    smsMessageId: 'message',
  });
  expect(dashboardEntry({ kind: 'registers' })).toEqual({ selection: 'world-registers' });
  expect(dashboardEntry({ kind: 'settings', token: 'journals' })).toEqual({
    selection: 'journals',
  });
  expect(dashboardEntry({ kind: 'settings', token: null })).toEqual({ selection: 'configuration' });
});

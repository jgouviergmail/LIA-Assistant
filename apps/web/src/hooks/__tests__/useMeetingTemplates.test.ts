/**
 * useMeetingTemplates — the library with its batches (ADR-259): every write
 * returns the server's answer and updates the list in place; a batch appends
 * what was created and drops what was deleted, and hands the caller the
 * skipped refs and the preference-reset fact to tell the user.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import type { MeetingTemplateSummary } from '@/types/meetings';

const api = vi.hoisted(() => ({
  templates: vi.fn(),
  bulkDuplicateTemplates: vi.fn(),
  bulkDeleteTemplates: vi.fn(),
}));
vi.mock('@/lib/meetings/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/meetings/api')>();
  return { ...actual, meetingsApi: { ...actual.meetingsApi, ...api } };
});

import { useMeetingTemplates } from '../useMeetingTemplates';

function summary(over: Partial<MeetingTemplateSummary> = {}): MeetingTemplateSummary {
  return {
    ref: 'builtin:default_minutes',
    name: 'Meeting minutes',
    description: null,
    category: 'meeting',
    builtin: true,
    sections_count: 6,
    auto_selectable: true,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.templates.mockResolvedValue({
    items: [
      summary(),
      summary({ ref: 'user:1', name: 'Mine', category: 'custom', builtin: false }),
    ],
    max_user_templates: 50,
  });
});

describe('useMeetingTemplates — batches', () => {
  it('adds the created rows to the library after a batch duplicate', async () => {
    const created = summary({ ref: 'user:2', name: 'Meeting minutes', builtin: false });
    api.bulkDuplicateTemplates.mockResolvedValue({
      created: [created],
      skipped: [{ ref: 'builtin:nope', code: 'template_not_found' }],
    });
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let response: unknown;
    await act(async () => {
      response = await result.current.bulkDuplicate(['builtin:default_minutes', 'builtin:nope']);
    });

    expect(api.bulkDuplicateTemplates).toHaveBeenCalledWith({
      refs: ['builtin:default_minutes', 'builtin:nope'],
    });
    expect(response).toEqual({
      created: [created],
      skipped: [{ ref: 'builtin:nope', code: 'template_not_found' }],
    });
    expect(result.current.templates.map(t => t.ref)).toEqual([
      'builtin:default_minutes',
      'user:1',
      'user:2',
    ]);
  });

  it('drops the deleted rows after a batch delete and reports the preference reset', async () => {
    api.bulkDeleteTemplates.mockResolvedValue({
      deleted: ['user:1'],
      skipped: [],
      preference_reset: true,
    });
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let response: unknown;
    await act(async () => {
      response = await result.current.bulkDelete(['user:1']);
    });

    expect(api.bulkDeleteTemplates).toHaveBeenCalledWith({ refs: ['user:1'] });
    expect(response).toEqual({ deleted: ['user:1'], skipped: [], preference_reset: true });
    expect(result.current.templates.map(t => t.ref)).toEqual(['builtin:default_minutes']);
  });

  it('keeps the library and exposes the error when a batch fails', async () => {
    api.bulkDeleteTemplates.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let response: unknown = 'unset';
    await act(async () => {
      response = await result.current.bulkDelete(['user:1']);
    });

    expect(response).toBeNull();
    expect(result.current.error?.message).toBe('boom');
    expect(result.current.templates).toHaveLength(2);
  });
});

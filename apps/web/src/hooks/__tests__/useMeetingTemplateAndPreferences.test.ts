/**
 * Library and preferences hooks (ADR-259): the library loads once, every write
 * returns the server's row and updates the list in place, a failed write keeps
 * the previous value and exposes the error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import type {
  MeetingPreferences,
  MeetingTemplate,
  MeetingTemplateListResponse,
  MeetingTemplateSummary,
} from '@/types/meetings';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));
vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: api };
});
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { useMeetingPreferences } from '../useMeetingPreferences';
import { useMeetingTemplates } from '../useMeetingTemplates';

const builtin: MeetingTemplateSummary = {
  ref: 'builtin:default_minutes',
  name: 'Meeting minutes',
  description: 'Summary, topics…',
  category: 'meeting',
  builtin: true,
  sections_count: 6,
  auto_selectable: true,
};
const mine: MeetingTemplate = {
  ref: 'user:11111111-1111-1111-1111-111111111111',
  id: '11111111-1111-1111-1111-111111111111',
  name: 'Mine',
  description: null,
  category: 'custom',
  sections: [{ key: 'summary', label: 'Summary', instruction: 'i', kind: 'paragraph' }],
  builtin: false,
  builtin_key: null,
  auto_selectable: true,
};
const library: MeetingTemplateListResponse = { items: [builtin], max_user_templates: 50 };
const preferences: MeetingPreferences = {
  stt_engine: 'auto',
  language: 'auto',
  auto_email: false,
  keep_audio_hours: 0,
  default_template_ref: null,
  keep_audio_hours_max: 168,
};

beforeEach(() => {
  Object.values(api).forEach(fn => fn.mockReset());
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useMeetingTemplates', () => {
  it('loads the library and creates, updates and removes a user template in place', async () => {
    api.get.mockResolvedValueOnce(library);
    api.post.mockResolvedValueOnce(mine);
    api.put.mockResolvedValueOnce({ ...mine, name: 'Renamed' });
    api.delete.mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.get).toHaveBeenCalledWith('/meetings/templates');
    expect(result.current.templates).toEqual([builtin]);
    expect(result.current.maxUserTemplates).toBe(50);

    await act(async () => {
      await result.current.create({ duplicate_of: 'builtin:default_minutes', name: 'Mine' });
    });
    expect(api.post).toHaveBeenCalledWith('/meetings/templates', {
      duplicate_of: 'builtin:default_minutes',
      name: 'Mine',
    });
    expect(result.current.templates.map(t => t.ref)).toEqual([builtin.ref, mine.ref]);
    expect(result.current.templates[1]).toMatchObject({
      name: 'Mine',
      builtin: false,
      sections_count: 1,
    });

    await act(async () => {
      await result.current.update(mine.ref, {
        name: 'Renamed',
        description: null,
        category: 'custom',
        sections: mine.sections,
      });
    });
    expect(api.put).toHaveBeenCalledWith(`/meetings/templates/${mine.ref}`, {
      name: 'Renamed',
      description: null,
      category: 'custom',
      sections: mine.sections,
    });
    expect(result.current.templates[1].name).toBe('Renamed');

    await act(async () => {
      await result.current.remove(mine.ref);
    });
    expect(api.delete).toHaveBeenCalledWith(`/meetings/templates/${mine.ref}`);
    expect(result.current.templates.map(t => t.ref)).toEqual([builtin.ref]);
  });

  it('loads one template with its sections on demand', async () => {
    api.get.mockResolvedValueOnce(library).mockResolvedValueOnce(mine);
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let loaded: MeetingTemplate | null = null;
    await act(async () => {
      loaded = await result.current.load(mine.ref);
    });
    expect(api.get).toHaveBeenLastCalledWith(`/meetings/templates/${mine.ref}`);
    expect(loaded).toEqual(mine);
  });

  it('a failed write keeps the library and exposes the error', async () => {
    api.get.mockResolvedValueOnce(library);
    api.post.mockRejectedValueOnce(new Error('409'));
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let outcome: MeetingTemplate | null = mine;
    await act(async () => {
      outcome = await result.current.create({ duplicate_of: 'builtin:default_minutes' });
    });
    expect(outcome).toBeNull();
    expect(result.current.templates).toEqual([builtin]);
    expect(result.current.error?.message).toBe('409');
  });

  it('does not fetch when disabled', () => {
    const { result } = renderHook(() => useMeetingTemplates(false));
    expect(result.current.isLoading).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe('useMeetingPreferences', () => {
  it('loads and saves the preferences, the default template included', async () => {
    api.get.mockResolvedValueOnce(preferences);
    api.put.mockResolvedValueOnce({
      ...preferences,
      auto_email: true,
      default_template_ref: 'builtin:daily_standup',
    });
    const { result } = renderHook(() => useMeetingPreferences());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.save({
        stt_engine: 'auto',
        language: 'auto',
        auto_email: true,
        keep_audio_hours: 0,
        default_template_ref: 'builtin:daily_standup',
      });
    });
    expect(api.put).toHaveBeenCalledWith('/meetings/preferences', {
      stt_engine: 'auto',
      language: 'auto',
      auto_email: true,
      keep_audio_hours: 0,
      default_template_ref: 'builtin:daily_standup',
    });
    expect(result.current.preferences?.auto_email).toBe(true);
    expect(result.current.preferences?.default_template_ref).toBe('builtin:daily_standup');
  });

  it('does not fetch when disabled', async () => {
    const { result } = renderHook(() => useMeetingPreferences(false));
    expect(result.current.isLoading).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
  });
});

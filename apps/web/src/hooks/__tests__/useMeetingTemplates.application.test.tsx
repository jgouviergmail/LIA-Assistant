import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { MeetingTemplate, MeetingTemplateListResponse } from '@/types/meetings';

const { templates, createTemplate, useAuth } = vi.hoisted(() => ({
  templates: vi.fn(),
  createTemplate: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/meetings/api', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/meetings/api')>();
  return { ...original, meetingsApi: { ...original.meetingsApi, templates, createTemplate } };
});
import { useMeetingTemplates } from '../useMeetingTemplates';

const saved: MeetingTemplate = {
  ref: 'user:11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Controlled',
  description: null,
  category: 'custom',
  builtin: false,
  builtin_key: null,
  auto_selectable: true,
  sections: [
    { key: 'summary', label: 'Summary', instruction: 'Literal instruction', kind: 'paragraph' },
  ],
};
const library: MeetingTemplateListResponse = {
  items: [
    {
      ref: saved.ref,
      name: saved.name,
      description: null,
      category: 'custom',
      builtin: false,
      sections_count: 1,
      auto_selectable: true,
    },
  ],
  max_user_templates: 20,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  templates.mockResolvedValue(library);
});

describe('owned template state and native changes', () => {
  it('rereads only the addressed library without issuing a mutation', async () => {
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.templates).toEqual(library.items));
    act(() => publishApplicationResources('two', new Set(['meeting_templates'])));
    expect(templates).toHaveBeenCalledTimes(1);
    templates.mockResolvedValueOnce({
      ...library,
      items: [{ ...library.items[0], name: 'Updated' }],
    });
    act(() => publishApplicationResources('one', new Set(['meeting_templates'])));
    await waitFor(() => expect(result.current.templates[0].name).toBe('Updated'));
    expect(createTemplate).not.toHaveBeenCalled();
  });

  it('refuses an obsolete creation callback before any wire write', async () => {
    const { result, rerender } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.templates).toEqual(library.items));
    const obsolete = result.current.create;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(templates).toHaveBeenCalledTimes(2));
    await act(async () =>
      expect(await obsolete({ name: 'Created', sections: saved.sections })).toBeNull()
    );
    expect(createTemplate).not.toHaveBeenCalled();
  });

  it('hides prior library data and ignores late creation replies after an account change', async () => {
    const pending = Promise.withResolvers<MeetingTemplate>();
    createTemplate.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.templates).toEqual(library.items));
    let writing: Promise<MeetingTemplate | null> | undefined;
    act(() => {
      writing = result.current.create({ name: 'Created', sections: saved.sections });
    });
    await waitFor(() => expect(createTemplate).toHaveBeenCalledTimes(1));
    templates.mockImplementationOnce(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.templates).toEqual([]);
    await act(async () => {
      pending.resolve({ ...saved, name: 'Created' });
      expect(await writing).toBeNull();
    });
    expect(result.current.templates).toEqual([]);
    expect(result.current.isSaving).toBe(false);
  });

  it('keeps known templates when an addressed reread fails', async () => {
    const { result } = renderHook(() => useMeetingTemplates());
    await waitFor(() => expect(result.current.templates).toEqual(library.items));
    templates.mockRejectedValueOnce(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['meeting_templates'])));
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.templates).toEqual(library.items);
  });
});

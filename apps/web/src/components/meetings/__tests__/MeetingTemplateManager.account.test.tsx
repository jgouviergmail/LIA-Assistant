import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UseMeetingTemplatesReturn } from '@/hooks/useMeetingTemplates';
import type { MeetingTemplate } from '@/types/meetings';

const { useAuth, success, error } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('sonner', () => ({ toast: { success, error, info: vi.fn() } }));
vi.mock('@/components/meetings/MeetingTemplateLibrary', () => ({
  MeetingTemplateLibrary: ({ onEdit }: { onEdit: (ref: string) => void }) => (
    <button onClick={() => onEdit('user:controlled')}>Open controlled</button>
  ),
}));

import { MeetingTemplateManager } from '../MeetingTemplateManager';

const template: MeetingTemplate = {
  ref: 'user:controlled',
  id: 'controlled',
  name: 'Private account draft',
  description: null,
  category: 'custom',
  sections: [{ key: 'summary', label: 'Summary', instruction: 'Literal', kind: 'paragraph' }],
  builtin: false,
  builtin_key: null,
  auto_selectable: true,
};
function library(): UseMeetingTemplatesReturn {
  return {
    templates: [{ ...template, sections_count: 1 }],
    maxUserTemplates: 20,
    isLoading: false,
    isSaving: false,
    error: null,
    refetch: vi.fn(),
    load: vi.fn().mockResolvedValue(template),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    bulkDuplicate: vi.fn(),
    bulkDelete: vi.fn(),
  };
}
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
});

describe('meeting library account ownership', () => {
  it('discards the private form and local edits when the account changes, including A to B to A', async () => {
    const saved = library();
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateManager lng="en" library={saved} />
    );
    await user.click(screen.getByRole('button', { name: 'Open controlled' }));
    await screen.findByDisplayValue('Private account draft');
    await user.type(screen.getByLabelText('meetings.templates.form.name'), ' unsaved');
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<MeetingTemplateManager lng="en" library={library()} />);
    expect(screen.queryByDisplayValue('Private account draft unsaved')).toBeNull();
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender(<MeetingTemplateManager lng="en" library={saved} />);
    expect(screen.queryByDisplayValue('Private account draft unsaved')).toBeNull();
    expect(saved.update).not.toHaveBeenCalled();
  });

  it('ignores a late load after an account change', async () => {
    const pending = Promise.withResolvers<MeetingTemplate>();
    const saved = library();
    vi.mocked(saved.load).mockReturnValue(pending.promise);
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateManager lng="en" library={saved} />
    );
    await user.click(screen.getByRole('button', { name: 'Open controlled' }));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<MeetingTemplateManager lng="en" library={library()} />);
    await act(async () => pending.resolve(template));
    expect(screen.queryByDisplayValue('Private account draft')).toBeNull();
    expect(error).not.toHaveBeenCalled();
  });

  it('keeps the populated library mounted while refreshing', async () => {
    const saved = library();
    const { rerender } = renderWithProviders(<MeetingTemplateManager lng="en" library={saved} />);
    rerender(<MeetingTemplateManager lng="en" library={{ ...saved, isLoading: true }} />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Open controlled' })).toBeVisible()
    );
  });

  it('suppresses a late save receipt and toast after the old account leaves', async () => {
    const pending = Promise.withResolvers<MeetingTemplate>();
    const saved = library();
    vi.mocked(saved.update).mockReturnValue(pending.promise);
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateManager lng="en" library={saved} />
    );
    await user.click(screen.getByRole('button', { name: 'Open controlled' }));
    await screen.findByDisplayValue('Private account draft');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    expect(saved.update).toHaveBeenCalledTimes(1);
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<MeetingTemplateManager lng="en" library={library()} />);
    await act(async () => pending.resolve(template));
    expect(success).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
    expect(screen.queryByDisplayValue('Private account draft')).toBeNull();
  });
});

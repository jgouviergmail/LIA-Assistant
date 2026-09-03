/**
 * The « Change the format » dialog (ADR-259): the current template preselected,
 * two modes, a submit that stays refused while nothing would change, a cost
 * note always, a transcript note when the chosen template rewrites the whole
 * exchange.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingDetail, MeetingTemplateSummary } from '@/types/meetings';

const library = vi.hoisted(() => ({
  templates: [] as MeetingTemplateSummary[],
  isLoading: false,
  enabledCalls: [] as boolean[],
}));
vi.mock('@/hooks/useMeetingTemplates', () => ({
  useMeetingTemplates: (enabled: boolean) => {
    library.enabledCalls.push(enabled);
    return {
      templates: library.templates,
      maxUserTemplates: 50,
      isLoading: library.isLoading,
      isSaving: false,
      error: null,
      refetch: vi.fn(),
      load: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    };
  },
}));

import { ReformatDialog } from '../ReformatDialog';

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

const MEETING = {
  id: 'm1',
  template_ref: 'builtin:default_minutes',
  template_name: 'Meeting minutes',
  has_transcript: true,
} as Pick<MeetingDetail, 'id' | 'template_ref' | 'template_name' | 'has_transcript'>;

function render(over: Partial<React.ComponentProps<typeof ReformatDialog>> = {}) {
  const onSubmit = vi.fn();
  const onOpenChange = vi.fn();
  const utils = renderWithProviders(
    <ReformatDialog
      lng="en"
      open
      onOpenChange={onOpenChange}
      meeting={MEETING}
      isActing={false}
      onSubmit={onSubmit}
      {...over}
    />
  );
  return { ...utils, onSubmit, onOpenChange };
}

beforeEach(() => {
  library.templates = [
    summary(),
    summary({
      ref: 'builtin:transcript_clean',
      name: 'Clean transcript',
      category: 'transcript',
      auto_selectable: false,
    }),
  ];
  library.isLoading = false;
  library.enabledCalls = [];
});

describe('ReformatDialog', () => {
  it('names itself, preselects the current template, and refuses to submit while nothing changes', () => {
    const { onSubmit } = render();
    expect(
      screen.getByRole('dialog', { name: 'meetings.detail.reformat.title' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'meetings.detail.reformat.template_label' })
    ).toHaveTextContent('Meeting minutes');
    expect(
      screen.getByRole('radio', { name: 'meetings.detail.reformat.mode_replace' })
    ).toBeChecked();
    expect(screen.getByText('meetings.detail.reformat.cost_note')).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'meetings.detail.reformat.submit' });
    expect(submit).toHaveAttribute('aria-disabled', 'true');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('loads the library only while open', () => {
    render({ open: false });
    expect(library.enabledCalls).toContain(false);
    expect(library.enabledCalls).not.toContain(true);
  });

  it('submits new minutes from the same transcript with the same template', async () => {
    const { user, onSubmit } = render();
    await user.click(screen.getByRole('radio', { name: 'meetings.detail.reformat.mode_new' }));
    const submit = screen.getByRole('button', { name: 'meetings.detail.reformat.submit' });
    expect(submit).toHaveAttribute('aria-disabled', 'false');
    await user.click(submit);
    expect(onSubmit).toHaveBeenCalledWith({ template_ref: 'builtin:default_minutes', mode: 'new' });
  });

  it('warns when the chosen template rewrites the whole transcript', () => {
    render({ meeting: { ...MEETING, template_ref: 'builtin:transcript_clean' } });
    expect(screen.getByText('meetings.detail.reformat.transcript_note')).toBeInTheDocument();
  });

  it('shows the library loading and closes on Escape', async () => {
    library.isLoading = true;
    const { user, onOpenChange } = render();
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-busy', 'true');
    await user.keyboard('{Escape}');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('does not submit twice while acting', async () => {
    const { user, onSubmit } = render({ isActing: true });
    await user.click(screen.getByRole('radio', { name: 'meetings.detail.reformat.mode_new' }));
    await user.click(screen.getByRole('button', { name: /meetings\.detail\.reformat\.submit/ }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

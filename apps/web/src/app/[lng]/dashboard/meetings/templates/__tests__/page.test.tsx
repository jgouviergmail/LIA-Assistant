/**
 * The template library page (ADR-259, recomposed): the two sections, the
 * batches with their toasts (created / deleted / skipped / preference reset),
 * the read-only preview with « add to my templates », and the form for
 * creating and editing only — a duplicate never opens a form.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { MeetingTemplate, MeetingTemplateSummary } from '@/types/meetings';

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const library = vi.hoisted(() => ({
  templates: [] as MeetingTemplateSummary[],
  maxUserTemplates: 50,
  isLoading: false,
  isSaving: false,
  load: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  bulkDuplicate: vi.fn(),
  bulkDelete: vi.fn(),
}));
vi.mock('@/hooks/useMeetingTemplates', () => ({
  useMeetingTemplates: () => ({ ...library, error: null, refetch: vi.fn() }),
}));
const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));
const confirm = vi.hoisted(() => ({ answer: true, calls: [] as unknown[] }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({
    confirm: async (options: unknown) => {
      confirm.calls.push(options);
      return confirm.answer;
    },
    confirmDialog: null,
  }),
}));

import TemplatesPage from '../page';

const params = Promise.resolve({ lng: 'en' });

function summary(over: Partial<MeetingTemplateSummary> = {}): MeetingTemplateSummary {
  return {
    ref: 'builtin:default_minutes',
    name: 'Meeting minutes',
    description: 'Summary, topics, decisions.',
    category: 'meeting',
    builtin: true,
    sections_count: 6,
    auto_selectable: true,
    ...over,
  };
}

function full(over: Partial<MeetingTemplate> = {}): MeetingTemplate {
  return {
    ref: 'builtin:default_minutes',
    id: null,
    name: 'Meeting minutes',
    description: 'Summary, topics, decisions.',
    category: 'meeting',
    sections: [
      { key: 'summary', label: 'Summary', instruction: 'Prose.', kind: 'paragraph' },
      { key: 'decisions', label: 'Decisions', instruction: 'Bullets.', kind: 'bullets' },
    ],
    builtin: true,
    builtin_key: null,
    auto_selectable: true,
    ...over,
  };
}

const MINE = full({
  ref: 'user:1',
  id: '1',
  name: 'Mine',
  description: null,
  category: 'custom',
  builtin: false,
});

beforeEach(() => {
  vi.clearAllMocks();
  library.templates = [
    summary(),
    summary({ ref: 'user:1', name: 'Mine', description: null, category: 'custom', builtin: false }),
  ];
  library.maxUserTemplates = 50;
  library.isLoading = false;
  library.isSaving = false;
  library.load.mockImplementation(async (ref: string) => (ref === 'user:1' ? MINE : full()));
  library.create.mockResolvedValue(MINE);
  library.update.mockResolvedValue(MINE);
  library.bulkDuplicate.mockResolvedValue({
    created: [summary({ ref: 'user:2', name: 'Meeting minutes', builtin: false })],
    skipped: [],
  });
  library.bulkDelete.mockResolvedValue({
    deleted: ['user:1'],
    skipped: [],
    preference_reset: false,
  });
  confirm.answer = true;
  confirm.calls = [];
});

async function openCategory(
  user: ReturnType<typeof renderWithProviders>['user'],
  region: HTMLElement,
  category: string
) {
  await user.click(
    within(region).getByRole('button', {
      name: new RegExp(`meetings\\.templates\\.category\\.${category}`),
    })
  );
}

describe('TemplatesPage', () => {
  it('announces the first load', () => {
    library.isLoading = true;
    renderWithProviders(<TemplatesPage params={params} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('adds a built-in to my templates in one click and reports it', async () => {
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const builtins = screen.getByRole('region', { name: 'meetings.templates.builtin_title' });
    await openCategory(user, builtins, 'meeting');
    const row = within(builtins).getByRole('listitem', { name: 'Meeting minutes' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.add_to_mine' }));
    await waitFor(() =>
      expect(library.bulkDuplicate).toHaveBeenCalledWith(['builtin:default_minutes'])
    );
    expect(toast.success).toHaveBeenCalledWith('meetings.templates.added');
    // No form opened: the user edits from « My templates » afterwards.
    expect(screen.queryByLabelText('meetings.templates.form.name')).not.toBeInTheDocument();
  });

  it('reports what a batch skipped', async () => {
    library.bulkDuplicate.mockResolvedValue({
      created: [],
      skipped: [{ ref: 'builtin:default_minutes', code: 'template_limit_reached' }],
    });
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const builtins = screen.getByRole('region', { name: 'meetings.templates.builtin_title' });
    await openCategory(user, builtins, 'meeting');
    const row = within(builtins).getByRole('listitem', { name: 'Meeting minutes' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.add_to_mine' }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('meetings.templates.skipped'));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('deletes one of my templates after confirmation and warns when the default format was reset', async () => {
    library.bulkDelete.mockResolvedValue({
      deleted: ['user:1'],
      skipped: [],
      preference_reset: true,
    });
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const mine = screen.getByRole('region', { name: 'meetings.templates.mine_title' });
    await openCategory(user, mine, 'custom');
    const row = within(mine).getByRole('listitem', { name: 'Mine' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.delete' }));
    expect(confirm.calls).toHaveLength(1);
    await waitFor(() => expect(library.bulkDelete).toHaveBeenCalledWith(['user:1']));
    expect(toast.success).toHaveBeenCalledWith('meetings.templates.deleted');
    expect(toast.info).toHaveBeenCalledWith('meetings.templates.preference_reset');
  });

  it('does nothing when the deletion is declined', async () => {
    confirm.answer = false;
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const mine = screen.getByRole('region', { name: 'meetings.templates.mine_title' });
    await openCategory(user, mine, 'custom');
    const row = within(mine).getByRole('listitem', { name: 'Mine' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.delete' }));
    expect(library.bulkDelete).not.toHaveBeenCalled();
  });

  it('duplicates one of my templates in place, without a form', async () => {
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const mine = screen.getByRole('region', { name: 'meetings.templates.mine_title' });
    await openCategory(user, mine, 'custom');
    const row = within(mine).getByRole('listitem', { name: 'Mine' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.duplicate' }));
    await waitFor(() => expect(library.bulkDuplicate).toHaveBeenCalledWith(['user:1']));
    expect(screen.queryByLabelText('meetings.templates.form.name')).not.toBeInTheDocument();
  });

  it('previews a built-in read-only, adds it from the preview, and comes back', async () => {
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const builtins = screen.getByRole('region', { name: 'meetings.templates.builtin_title' });
    await openCategory(user, builtins, 'meeting');
    const row = within(builtins).getByRole('listitem', { name: 'Meeting minutes' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.preview' }));
    expect(await screen.findByText('Prose.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.templates.add_to_mine' }));
    await waitFor(() =>
      expect(library.bulkDuplicate).toHaveBeenCalledWith(['builtin:default_minutes'])
    );
    await user.click(screen.getByRole('button', { name: 'meetings.templates.back_to_library' }));
    expect(
      screen.getByRole('region', { name: 'meetings.templates.mine_title' })
    ).toBeInTheDocument();
  });

  it('edits a user template and saves it in place', async () => {
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const mine = screen.getByRole('region', { name: 'meetings.templates.mine_title' });
    await openCategory(user, mine, 'custom');
    const row = within(mine).getByRole('listitem', { name: 'Mine' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.edit' }));
    const name = await screen.findByLabelText('meetings.templates.form.name');
    await user.type(name, ' v2');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    await waitFor(() =>
      expect(library.update).toHaveBeenCalledWith('user:1', {
        name: 'Mine v2',
        description: null,
        category: 'custom',
        sections: MINE.sections,
      })
    );
  });

  it('creates a template from scratch with one section', async () => {
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.templates.new' }));
    const name = await screen.findByLabelText('meetings.templates.form.name');
    await user.type(name, 'Retro');
    const [heading] = screen.getAllByLabelText('meetings.settings.section_label');
    await user.clear(heading);
    await user.type(heading, 'Went well');
    await user.type(screen.getByLabelText('meetings.settings.section_instruction'), 'List it.');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    await waitFor(() => expect(library.create).toHaveBeenCalled());
    const request = library.create.mock.calls[0][0];
    expect(request.name).toBe('Retro');
    expect(request.sections).toHaveLength(1);
    // A brand-new template's keys follow the headings the user typed: nothing
    // refers to them yet, so they are derived once, at creation.
    expect(request.sections[0].key).toBe('went_well');
    expect(toast.success).toHaveBeenCalledWith('meetings.templates.saved');
  });

  it('refuses to create beyond the cap and says so', async () => {
    library.maxUserTemplates = 1;
    const { user } = renderWithProviders(<TemplatesPage params={params} />);
    const create = screen.getByRole('button', { name: 'meetings.templates.new' });
    expect(create).toHaveAttribute('aria-disabled', 'true');
    await user.click(create);
    expect(screen.queryByLabelText('meetings.templates.form.name')).not.toBeInTheDocument();
    expect(screen.getByText('meetings.templates.limit_reached')).toBeInTheDocument();
  });
});

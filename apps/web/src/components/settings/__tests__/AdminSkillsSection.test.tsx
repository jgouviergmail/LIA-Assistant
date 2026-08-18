/**
 * AdminSkillsSection — the admin skill catalogue: loading / empty / listing
 * (user-scoped skills must never leak in), the **file import** with its
 * server-detail error passthrough, the catalogue reload, the system-level
 * toggle, description translation, download, the confirm-gated deletion, and
 * the description editor (prefilled from the admin's own language).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, fireEvent } from '@/__tests__/test-utils';
import type { Skill, useSkills as useSkillsFn } from '@/hooks/useSkills';

const { useSkills } = vi.hoisted(() => ({ useSkills: vi.fn() }));
vi.mock('@/hooks/useSkills', () => ({ useSkills }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { AdminSkillsSection } from '../AdminSkillsSection';

const I18N = 'settings.skills';
type SkillsHook = ReturnType<typeof useSkillsFn>;

function skill(over: Partial<Skill> = {}): Skill {
  return {
    name: 'invoice-parser',
    description: 'Parses invoices',
    descriptions: null,
    scope: 'admin',
    category: null,
    priority: 0,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    admin_enabled: true,
    ...over,
  };
}

function hook(over: Partial<SkillsHook> = {}) {
  return {
    skills: [skill()],
    loading: false,
    error: null,
    refetch: vi.fn(),
    reloadSkills: vi.fn().mockResolvedValue({ count: 3 }),
    reloading: false,
    importAdminSkill: vi.fn().mockResolvedValue({ name: 'imported-skill' }),
    deleteAdminSkill: vi.fn().mockResolvedValue(undefined),
    adminSystemToggleSkill: vi.fn().mockResolvedValue({ admin_enabled: false }),
    togglingSystem: false,
    translateSkillDescription: vi.fn().mockResolvedValue({ ok: true }),
    translating: false,
    updateAdminSkillDescription: vi.fn().mockResolvedValue({ ok: true }),
    updatingDescription: false,
    downloadSkill: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

function render() {
  return renderWithProviders(
    <AdminSkillsSection lng="en" />
  );
}

/** The import control is a deliberately hidden native file input. */
function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  if (!input) throw new Error('no file input rendered');
  return input as HTMLInputElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  useSkills.mockReturnValue(hook());
});

describe('AdminSkillsSection — listing', () => {
  it('shows the empty state when no admin skill exists', () => {
    useSkills.mockReturnValue(hook({ skills: [] }));
    render();
    expect(screen.getByText(`${I18N}.empty`)).toBeInTheDocument();
  });

  it('never lists user-scoped skills in the admin catalogue', () => {
    useSkills.mockReturnValue(
      hook({ skills: [skill(), skill({ name: 'personal-note', scope: 'user' })] })
    );
    render();
    expect(screen.getByText('invoice-parser')).toBeInTheDocument();
    expect(screen.queryByText('personal-note')).not.toBeInTheDocument();
  });
});

describe('AdminSkillsSection — import', () => {
  it('imports the picked file and confirms with the created name', async () => {
    const importAdminSkill = vi.fn().mockResolvedValue({ name: 'imported-skill' });
    useSkills.mockReturnValue(hook({ importAdminSkill }));
    const { container } = render();
    const file = new File(['# skill'], 'skill.md', { type: 'text/markdown' });
    fireEvent.change(fileInput(container), { target: { files: [file] } });
    await waitFor(() => expect(importAdminSkill).toHaveBeenCalledWith(file));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.import_success`);
  });

  it('surfaces the server detail when the import is rejected', async () => {
    const importAdminSkill = vi.fn().mockRejectedValue(new Error('skill already exists'));
    useSkills.mockReturnValue(hook({ importAdminSkill }));
    const { container } = render();
    const file = new File(['# skill'], 'skill.md', { type: 'text/markdown' });
    fireEvent.change(fileInput(container), { target: { files: [file] } });
    // The API detail wins over the generic fallback.
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('skill already exists'));
  });

  it('ignores a cancelled file picker', async () => {
    const importAdminSkill = vi.fn();
    useSkills.mockReturnValue(hook({ importAdminSkill }));
    const { container } = render();
    fireEvent.change(fileInput(container), { target: { files: [] } });
    expect(importAdminSkill).not.toHaveBeenCalled();
  });
});

describe('AdminSkillsSection — catalogue actions', () => {
  it('reloads the catalogue and reports how many skills were found', async () => {
    const reloadSkills = vi.fn().mockResolvedValue({ count: 7 });
    useSkills.mockReturnValue(hook({ reloadSkills }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.reload_button` }));
    await waitFor(() => expect(reloadSkills).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.reload_success`);
  });

  it('reports a failed reload', async () => {
    useSkills.mockReturnValue(hook({ reloadSkills: vi.fn().mockRejectedValue(new Error('x')) }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.reload_button` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(`${I18N}.reload_error`));
  });

  it('toggles a skill system-wide and words the toast from the server state', async () => {
    const adminSystemToggleSkill = vi.fn().mockResolvedValue({ admin_enabled: false });
    useSkills.mockReturnValue(hook({ adminSystemToggleSkill }));
    const { user } = render();
    await user.click(screen.getByRole('switch', { name: `${I18N}.toggle_skill` }));
    await waitFor(() => expect(adminSystemToggleSkill).toHaveBeenCalledWith('invoice-parser'));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.disabled_toast`);
  });

  it('translates a description', async () => {
    const translateSkillDescription = vi.fn().mockResolvedValue({ ok: true });
    useSkills.mockReturnValue(hook({ translateSkillDescription }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.translate_button_label` }));
    await waitFor(() => expect(translateSkillDescription).toHaveBeenCalledWith('invoice-parser'));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.translate_success`);
  });

  it('downloads a skill bundle and reports a failure', async () => {
    const downloadSkill = vi.fn().mockRejectedValue(new Error('nope'));
    useSkills.mockReturnValue(hook({ downloadSkill }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.download_button` }));
    await waitFor(() => expect(downloadSkill).toHaveBeenCalledWith('invoice-parser', true));
    expect(toast.error).toHaveBeenCalledWith(`${I18N}.download_error`);
  });
});

describe('AdminSkillsSection — destructive & editing', () => {
  it('deletes a skill only after the confirmation is validated', async () => {
    const deleteAdminSkill = vi.fn().mockResolvedValue(undefined);
    useSkills.mockReturnValue(hook({ deleteAdminSkill }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.delete_admin_button` }));
    await screen.findByText(`${I18N}.delete_admin_confirm_title`);
    expect(deleteAdminSkill).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(deleteAdminSkill).toHaveBeenCalledWith('invoice-parser'));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.delete_admin_success`);
  });

  it('edits a description prefilled from the admin language and saves it', async () => {
    const updateAdminSkillDescription = vi.fn().mockResolvedValue({ ok: true });
    useSkills.mockReturnValue(
      hook({
        skills: [skill({ descriptions: { en: 'English text', fr: 'Texte FR' } })],
        updateAdminSkillDescription,
      })
    );
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.edit_description_button` }));
    const textarea = await screen.findByPlaceholderText(`${I18N}.edit_description_label`);
    // Prefilled with the admin's own language, not the raw fallback.
    expect(textarea).toHaveValue('English text');
    await user.clear(textarea);
    await user.type(textarea, 'Reworded description');
    await user.click(screen.getByRole('button', { name: `${I18N}.edit_description_submit` }));
    await waitFor(() =>
      expect(updateAdminSkillDescription).toHaveBeenCalledWith(
        'invoice-parser',
        'Reworded description',
        'en'
      )
    );
  });

  it('refuses to save a description shorter than the 10-character minimum', async () => {
    const updateAdminSkillDescription = vi.fn();
    useSkills.mockReturnValue(hook({ updateAdminSkillDescription }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `${I18N}.edit_description_button` }));
    const textarea = await screen.findByPlaceholderText(`${I18N}.edit_description_label`);
    await user.clear(textarea);
    await user.type(textarea, 'too short');
    expect(screen.getByRole('button', { name: `${I18N}.edit_description_submit` })).toBeDisabled();
    expect(updateAdminSkillDescription).not.toHaveBeenCalled();
  });
});

/**
 * Skills gallery flow (UXR Lot 10, B12) — cards open the detail modal,
 * provenance warning on user skills, declared channels with the "text"
 * fallback, URL-import dialog contract, and the pure mappers.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useSkills } = vi.hoisted(() => ({ useSkills: vi.fn() }));
vi.mock('@/hooks/useSkills', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useSkills')>();
  return { ...original, useSkills };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { SkillsSettings } from '../SkillsSettings';
import { displayedChannels } from '../SkillDetailModal';
import { ImportFromUrlDialog, urlImportErrorKey } from '../ImportFromUrlDialog';
import type { Skill, useSkills as useSkillsFn } from '@/hooks/useSkills';

type SkillsHook = ReturnType<typeof useSkillsFn>;

function skill(over: Partial<Skill> = {}): Skill {
  return {
    name: 'my-skill',
    description: 'Does things.',
    descriptions: null,
    scope: 'user',
    category: 'utility',
    priority: 50,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    outputs: null,
    ...over,
  };
}

function hook(over: Partial<SkillsHook> = {}) {
  return {
    skills: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
    importSkill: vi.fn(),
    importFromUrl: vi.fn(),
    importingFromUrl: false,
    deleteSkill: vi.fn(),
    deleting: false,
    toggleSkill: vi.fn().mockResolvedValue({ skill_name: 'my-skill', enabled_for_user: false }),
    toggling: false,
    downloadSkill: vi.fn(),
    ...over,
  };
}

function renderSkills() {
  return renderWithProviders(
    <SkillsSettings lng="en" />
  );
}

beforeEach(() => vi.clearAllMocks());

describe('SkillsSettings gallery', () => {
  it('opens the detail modal from a card, with provenance warning for user skills', async () => {
    useSkills.mockReturnValue(hook({ skills: [skill()] }));
    const { user } = renderSkills();
    await user.click(screen.getByRole('button', { name: /settings\.skills\.user_section_title/ }));
    await user.click(
      screen.getByRole('button', { name: /settings\.skills\.gallery\.open_details/ })
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('settings.skills.gallery.provenance_warning')).toBeInTheDocument();
    // Undeclared channels ⇒ the "text" default chip + the undeclared note.
    expect(screen.getByText('settings.skills.gallery.channel_text')).toBeInTheDocument();
    expect(screen.getByText('settings.skills.gallery.channels_undeclared')).toBeInTheDocument();
  });

  it('admin skills show no provenance warning and their declared channels', async () => {
    useSkills.mockReturnValue(
      hook({ skills: [skill({ scope: 'admin', outputs: ['text', 'frame'] })] })
    );
    const { user } = renderSkills();
    await user.click(screen.getByRole('button', { name: /settings\.skills\.admin_section_title/ }));
    await user.click(
      screen.getByRole('button', { name: /settings\.skills\.gallery\.open_details/ })
    );
    expect(screen.queryByText('settings.skills.gallery.provenance_warning')).toBeNull();
    expect(screen.getByText('settings.skills.gallery.channel_frame')).toBeInTheDocument();
    expect(screen.queryByText('settings.skills.gallery.channels_undeclared')).toBeNull();
  });

  it('the inline card switch toggles without opening the modal', async () => {
    const toggleSkill = vi
      .fn()
      .mockResolvedValue({ skill_name: 'my-skill', enabled_for_user: false });
    useSkills.mockReturnValue(hook({ skills: [skill()], toggleSkill }));
    const { user } = renderSkills();
    await user.click(screen.getByRole('button', { name: /settings\.skills\.user_section_title/ }));
    await user.click(screen.getByRole('switch', { name: /settings\.skills\.toggle_skill/ }));
    expect(toggleSkill).toHaveBeenCalledWith('my-skill');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('deleting from the modal goes through the confirmation dialog', async () => {
    const deleteSkill = vi.fn().mockResolvedValue(undefined);
    useSkills.mockReturnValue(hook({ skills: [skill()], deleteSkill }));
    const { user } = renderSkills();
    await user.click(screen.getByRole('button', { name: /settings\.skills\.user_section_title/ }));
    await user.click(
      screen.getByRole('button', { name: /settings\.skills\.gallery\.open_details/ })
    );
    await user.click(screen.getByRole('button', { name: /settings\.skills\.delete_button/ }));
    expect(screen.getByText('settings.skills.delete_confirm_title')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /common\.delete/ }));
    expect(deleteSkill).toHaveBeenCalledWith('my-skill');
  });
});

describe('ImportFromUrlDialog', () => {
  it('refuses non-https input and imports on a valid one', async () => {
    const onImport = vi.fn().mockResolvedValue(skill({ name: 'net-skill' }));
    const onOpenChange = vi.fn();
    const { user } = renderWithProviders(
      <ImportFromUrlDialog
        open
        t={(key: string) => key}
        onOpenChange={onOpenChange}
        onImport={onImport}
        importing={false}
      />
    );
    const confirmButton = screen.getByRole('button', {
      name: /settings\.skills\.url_import\.confirm/,
    });
    const input = screen.getByRole('textbox', { name: 'settings.skills.url_import.input_label' });
    await user.type(input, 'http://example.com/skill.zip');
    expect(confirmButton).toBeDisabled();
    await user.clear(input);
    await user.type(input, 'https://example.com/skill.zip');
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);
    expect(onImport).toHaveBeenCalledWith('https://example.com/skill.zip');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows the provenance warning before importing', () => {
    renderWithProviders(
      <ImportFromUrlDialog
        open
        t={(key: string) => key}
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        importing={false}
      />
    );
    expect(screen.getByText('settings.skills.gallery.provenance_warning')).toBeInTheDocument();
  });
});

describe('pure mappers', () => {
  it('displayedChannels falls back to text when undeclared', () => {
    expect(displayedChannels({ outputs: null })).toEqual({
      channels: ['text'],
      declared: false,
    });
    expect(displayedChannels({ outputs: [] })).toEqual({ channels: ['text'], declared: false });
    expect(displayedChannels({ outputs: ['frame', 'text'] })).toEqual({
      channels: ['frame', 'text'],
      declared: true,
    });
  });

  it('urlImportErrorKey maps every stable backend prefix', () => {
    expect(urlImportErrorKey('url_not_https: only https')).toBe(
      'settings.skills.url_import.error_not_https'
    );
    expect(urlImportErrorKey('url_blocked: private')).toBe(
      'settings.skills.url_import.error_blocked'
    );
    expect(urlImportErrorKey('url_too_large: cap')).toBe(
      'settings.skills.url_import.error_too_large'
    );
    expect(urlImportErrorKey('url_not_skill_content: html')).toBe(
      'settings.skills.url_import.error_not_skill'
    );
    expect(urlImportErrorKey('url_fetch_failed: HTTP 500')).toBe(
      'settings.skills.url_import.error_fetch'
    );
    expect(urlImportErrorKey('anything else')).toBe('settings.skills.import_error');
  });
});

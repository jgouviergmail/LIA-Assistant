/**
 * SkillsSettings — the loading, error (with retry) and populated states.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useSkills } = vi.hoisted(() => ({ useSkills: vi.fn() }));
vi.mock('@/hooks/useSkills', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useSkills')>();
  return { ...original, useSkills };
});
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
const { usePlugins } = vi.hoisted(() => ({ usePlugins: vi.fn() }));
vi.mock('@/hooks/usePlugins', () => ({ usePlugins }));
const { useAppConfig } = vi.hoisted(() => ({ useAppConfig: vi.fn() }));
vi.mock('@/hooks/useAppConfig', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useAppConfig')>();
  return { ...original, useAppConfig };
});

import { SkillsSettings } from '../SkillsSettings';
import type { useSkills as useSkillsFn, Skill } from '@/hooks/useSkills';

type SkillsHook = ReturnType<typeof useSkillsFn>;

// SkillsSettings renders inside an open SettingsSection card (value
// "skills"), so its body is visible on mount.
function renderSkills() {
  return renderWithProviders(<SkillsSettings lng="en" />);
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
    toggleSkill: vi.fn(),
    toggling: false,
    downloadSkill: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAppConfig.mockReturnValue({ config: null, loading: false, error: null });
  usePlugins.mockReturnValue({ plugins: [], total: 0, loading: false });
});

function userSkill(over: Partial<Skill> = {}): Skill {
  return {
    name: 'alpha',
    description: 'A user skill.',
    descriptions: null,
    scope: 'user',
    category: null,
    priority: 50,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    ...over,
  };
}

describe('SkillsSettings', () => {
  it('shows a loading spinner while skills load', () => {
    useSkills.mockReturnValue(hook({ loading: true }));
    renderSkills();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a retry that refetches', async () => {
    const refetch = vi.fn();
    useSkills.mockReturnValue(hook({ error: new Error('load failed'), refetch }));
    const { user } = renderSkills();
    expect(screen.getByText('settings.skills.load_error')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});

describe('SkillsSettings — plugin-owned skill lock (ADR-225 arbitrage F)', () => {
  async function openDetail(user: Awaited<ReturnType<typeof renderSkills>>['user']) {
    await user.click(screen.getByRole('button', { name: /settings.skills.user_section_title/ }));
    await user.click(screen.getByRole('button', { name: /settings.skills.gallery.open_details/ }));
  }

  it('refuses deletion of a plugin skill with an informative toast', async () => {
    useSkills.mockReturnValue(hook({ skills: [userSkill()] }));
    usePlugins.mockReturnValue({
      plugins: [{ id: 'p1', name: 'acme.tools', skill_names: ['alpha'], server_names: [] }],
      total: 1,
      loading: false,
    });
    const { user } = renderSkills();
    await openDetail(user);

    await user.click(screen.getByRole('button', { name: 'settings.skills.delete_button' }));

    expect(toast.info).toHaveBeenCalledWith('settings.plugins.component_locked');
    expect(screen.queryByText('settings.skills.delete_confirm_title')).not.toBeInTheDocument();
  });

  it('still lets a manual skill reach the delete confirmation', async () => {
    useSkills.mockReturnValue(hook({ skills: [userSkill()] }));
    const { user } = renderSkills();
    await openDetail(user);

    await user.click(screen.getByRole('button', { name: 'settings.skills.delete_button' }));

    expect(toast.info).not.toHaveBeenCalled();
    expect(screen.getByText('settings.skills.delete_confirm_title')).toBeInTheDocument();
  });
});

describe('SkillsSettings — the skill library (ADR-327)', () => {
  const both = {
    capabilities: {
      skills: { enabled: true, family: 'reach' },
      skill_library: { enabled: true, family: 'reach' },
    },
  };

  it('offers « Find skills » when both switches are on, and opens the library', async () => {
    useSkills.mockReturnValue(hook());
    useAppConfig.mockReturnValue({ config: both, loading: false, error: null });
    const { user } = renderSkills();

    await user.click(screen.getByRole('button', { name: 'settings.skills.library.button' }));

    expect(await screen.findByText('settings.skills.library.title')).toBeInTheDocument();
  });

  it('offers nothing when the library is switched off', () => {
    useSkills.mockReturnValue(hook());
    useAppConfig.mockReturnValue({
      config: {
        capabilities: { ...both.capabilities, skill_library: { enabled: false, family: 'reach' } },
      },
      loading: false,
      error: null,
    });
    renderSkills();

    expect(
      screen.queryByRole('button', { name: 'settings.skills.library.button' })
    ).not.toBeInTheDocument();
  });
});

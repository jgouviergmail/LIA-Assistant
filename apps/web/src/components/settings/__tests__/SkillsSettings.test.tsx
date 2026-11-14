/**
 * SkillsSettings — the loading, error (with retry) and populated states.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'skills-owner' } }) }));

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
    dormantAfterDays: 60,
    settleDormant: vi.fn(),
    settlingDormant: false,
    restorePreviousSkill: vi.fn(),
    restoringPrevious: false,
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
    await user.click(screen.getByText('settings.skills.user_section_title'));
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

describe('SkillsSettings — the two scopes are standard folds', () => {
  function adminSkill(over: Partial<Skill> = {}): Skill {
    return userSkill({ name: 'beta', scope: 'admin', ...over });
  }

  it('renders both scopes as native disclosures, closed on arrival, with exact counts', () => {
    useSkills.mockReturnValue(
      hook({ skills: [adminSkill(), adminSkill({ name: 'gamma' }), userSkill()] })
    );
    const { container } = renderSkills();

    const folds = container.querySelectorAll('details');
    expect(folds).toHaveLength(2);
    folds.forEach(fold => expect(fold.open).toBe(false));
    // Folded, the count is what the reader chooses from.
    const adminSummary = screen.getByText('settings.skills.admin_section_title').closest('summary');
    const userSummary = screen.getByText('settings.skills.user_section_title').closest('summary');
    expect(adminSummary).toHaveTextContent('2');
    expect(userSummary).toHaveTextContent('1');
    // Closed means unmounted: no card of either scope yet.
    expect(
      screen.queryByRole('button', { name: /settings\.skills\.gallery\.open_details/ })
    ).not.toBeInTheDocument();
  });

  it('opens the person’s own scope on its summary and lists its skills', async () => {
    useSkills.mockReturnValue(hook({ skills: [userSkill()] }));
    const { user, container } = renderSkills();

    await user.click(screen.getByText('settings.skills.user_section_title'));

    expect(container.querySelector('details')?.open).toBe(true);
    expect(
      screen.getByRole('button', { name: /settings\.skills\.gallery\.open_details/ })
    ).toBeInTheDocument();
  });

  it('keeps the import actions reachable while every scope is folded', () => {
    useSkills.mockReturnValue(hook({ skills: [userSkill()] }));
    renderSkills();

    // A fold unmounts its content: the toolbar lives above the folds.
    expect(
      screen.getByRole('button', { name: 'settings.skills.import_button' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'settings.skills.url_import.button' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'settings.skills.guide_button' })
    ).toBeInTheDocument();
  });

  it('hides the admin scope when the instance ships none, and says so in the empty user one', async () => {
    useSkills.mockReturnValue(hook({ skills: [] }));
    const { user, container } = renderSkills();

    expect(container.querySelectorAll('details')).toHaveLength(1);
    expect(screen.queryByText('settings.skills.admin_section_title')).not.toBeInTheDocument();
    await user.click(screen.getByText('settings.skills.user_section_title'));
    expect(screen.getByText('settings.skills.empty')).toBeInTheDocument();
  });

  it('opens the file picker from the primary import action', async () => {
    useSkills.mockReturnValue(hook());
    const { user, container } = renderSkills();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const pick = vi.spyOn(input as HTMLInputElement, 'click');

    await user.click(screen.getByRole('button', { name: 'settings.skills.import_button' }));

    expect(pick).toHaveBeenCalled();
  });
});

describe("SkillsSettings — a skill's life (lot 14)", () => {
  const COUNTED = '2026-11-13T09:00:00Z';

  function dormant(name: string): Skill {
    return userSkill({
      name,
      skill_id: `id-${name}`,
      use_count: 0,
      counted_since: COUNTED,
      dormant: true,
    });
  }

  it('says, on each card, how often its skill was used and greys a dormant one', async () => {
    useSkills.mockReturnValue(
      hook({
        skills: [
          userSkill({
            use_count: 2,
            counted_since: COUNTED,
            last_used_at: '2026-12-01T09:00:00Z',
          }),
          dormant('idle'),
        ],
      })
    );
    const { user } = renderSkills();

    await user.click(screen.getByText('settings.skills.user_section_title'));

    expect(screen.getByText('settings.skills.usage.used')).toBeInTheDocument();
    expect(screen.getByText('settings.skills.usage.none')).toBeInTheDocument();
    expect(screen.getAllByText('settings.skills.usage.dormant_badge')).toHaveLength(1);
  });

  it('proposes switching off the dormant skills before any fold is opened', async () => {
    const settleDormant = vi.fn().mockResolvedValue({
      decision: 'switch_off',
      settled: ['idle', 'old'],
    });
    useSkills.mockReturnValue(hook({ skills: [dormant('idle'), dormant('old')], settleDormant }));
    const { user } = renderSkills();

    const notice = screen.getByRole('region', { name: 'settings.skills.dormant.title' });
    await user.click(screen.getByRole('button', { name: 'settings.skills.dormant.switch_off' }));

    expect(notice).toBeInTheDocument();
    expect(settleDormant).toHaveBeenCalledWith(['id-idle', 'id-old'], 'switch_off');
    expect(toast.success).toHaveBeenCalledWith('settings.skills.dormant.switched_off_toast');
  });

  it('keeping them says the proposal waits a whole period again', async () => {
    const settleDormant = vi.fn().mockResolvedValue({ decision: 'keep', settled: ['idle'] });
    useSkills.mockReturnValue(hook({ skills: [dormant('idle')], settleDormant }));
    const { user } = renderSkills();

    await user.click(screen.getByRole('button', { name: 'settings.skills.dormant.keep' }));

    expect(settleDormant).toHaveBeenCalledWith(['id-idle'], 'keep');
    expect(toast.success).toHaveBeenCalledWith('settings.skills.dormant.kept_toast');
  });

  it('says so when the skills were used meanwhile and nothing was settled', async () => {
    const settleDormant = vi.fn().mockResolvedValue({ decision: 'switch_off', settled: [] });
    useSkills.mockReturnValue(hook({ skills: [dormant('idle')], settleDormant }));
    const { user } = renderSkills();

    await user.click(screen.getByRole('button', { name: 'settings.skills.dormant.switch_off' }));

    expect(toast.info).toHaveBeenCalledWith('settings.skills.dormant.nothing_settled');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('says a failed answer instead of pretending', async () => {
    const settleDormant = vi.fn().mockRejectedValue(new Error('offline'));
    useSkills.mockReturnValue(hook({ skills: [dormant('idle')], settleDormant }));
    const { user } = renderSkills();

    await user.click(screen.getByRole('button', { name: 'settings.skills.dormant.keep' }));

    expect(toast.error).toHaveBeenCalledWith('settings.skills.dormant.error');
  });

  async function openAlpha(user: Awaited<ReturnType<typeof renderSkills>>['user']) {
    await user.click(screen.getByText('settings.skills.user_section_title'));
    await user.click(screen.getByRole('button', { name: /settings.skills.gallery.open_details/ }));
  }

  it('restores the previous version once the person confirms', async () => {
    const restorePreviousSkill = vi.fn().mockResolvedValue(userSkill());
    useSkills.mockReturnValue(
      hook({
        skills: [userSkill({ previous_version_at: '2026-11-12T08:00:00Z' })],
        restorePreviousSkill,
      })
    );
    const { user } = renderSkills();
    await openAlpha(user);

    await user.click(screen.getByRole('button', { name: 'settings.skills.previous.restore' }));
    expect(restorePreviousSkill).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole('button', { name: 'settings.skills.previous.confirm_action' })
    );

    expect(restorePreviousSkill).toHaveBeenCalledWith('alpha');
    expect(toast.success).toHaveBeenCalledWith('settings.skills.previous.success');
  });

  it('says a failed restoration', async () => {
    const restorePreviousSkill = vi.fn().mockRejectedValue(new Error('gone'));
    useSkills.mockReturnValue(
      hook({
        skills: [userSkill({ previous_version_at: '2026-11-12T08:00:00Z' })],
        restorePreviousSkill,
      })
    );
    const { user } = renderSkills();
    await openAlpha(user);

    await user.click(screen.getByRole('button', { name: 'settings.skills.previous.restore' }));
    await user.click(
      screen.getByRole('button', { name: 'settings.skills.previous.confirm_action' })
    );

    expect(toast.error).toHaveBeenCalledWith('settings.skills.previous.error');
  });

  it('offers no way back when no previous version was kept', async () => {
    useSkills.mockReturnValue(hook({ skills: [userSkill({ previous_version_at: null })] }));
    const { user } = renderSkills();
    await openAlpha(user);

    expect(
      screen.queryByRole('button', { name: 'settings.skills.previous.restore' })
    ).not.toBeInTheDocument();
  });
});

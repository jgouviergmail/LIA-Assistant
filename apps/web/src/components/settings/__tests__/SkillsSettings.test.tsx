/**
 * SkillsSettings — the loading, error (with retry) and populated states.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

const { useSkills } = vi.hoisted(() => ({ useSkills: vi.fn() }));
vi.mock('@/hooks/useSkills', () => ({ useSkills }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { SkillsSettings } from '../SkillsSettings';
import type { useSkills as useSkillsFn } from '@/hooks/useSkills';

type SkillsHook = ReturnType<typeof useSkillsFn>;

// SkillsSettings always renders inside a collapsible SettingsSection (value
// "skills"); mount it expanded.
function renderSkills() {
  return renderWithProviders(
    <Accordion type="multiple" defaultValue={['skills']}>
      <SkillsSettings lng="en" />
    </Accordion>
  );
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

beforeEach(() => vi.clearAllMocks());

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

/**
 * DormantSkillsNotice — the proposal to switch off the skills nobody uses (lot 14).
 *
 * A proposal one cannot decline is a nag: both answers are offered, keyboard
 * reachable, and a busy answer keeps the focus where it is (aria-disabled plus
 * a guard, never `disabled`).
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { Skill } from '@/hooks/useSkills';
import type { SkillLifeTranslator } from '@/lib/skill-life';

import { DormantSkillsNotice } from '../DormantSkillsNotice';

function skill(name: string): Skill {
  return {
    name,
    description: `${name}.`,
    descriptions: null,
    scope: 'user',
    category: null,
    priority: 50,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    skill_id: `id-${name}`,
    dormant: true,
  };
}

const t: SkillLifeTranslator = key => key;

function renderNotice(skills: Skill[], busy = false, days: { value?: number } = { value: 60 }) {
  const onDecide = vi.fn();
  const view = renderWithProviders(
    <DormantSkillsNotice skills={skills} days={days.value} t={t} busy={busy} onDecide={onDecide} />
  );
  return { ...view, onDecide };
}

describe('DormantSkillsNotice', () => {
  it('says nothing when no skill sleeps', () => {
    const { container } = renderNotice([]);

    expect(container).toBeEmptyDOMElement();
  });

  it('says nothing when the server published no period to measure against', () => {
    const { container } = renderNotice([skill('notes')], false, {});

    expect(container).toBeEmptyDOMElement();
  });

  it('names every skill it proposes, under its own heading', () => {
    renderNotice([skill('weather-report'), skill('notes')]);

    const region = screen.getByRole('region', { name: 'settings.skills.dormant.title' });
    const items = screen.getAllByRole('listitem').map(item => item.textContent);
    expect(region).toContainElement(screen.getByRole('list'));
    expect(items).toEqual(['weather-report', 'notes']);
  });

  it('switches them off, or keeps them, on the person’s word', async () => {
    const { user, onDecide } = renderNotice([skill('notes')]);

    await user.click(screen.getByRole('button', { name: 'settings.skills.dormant.switch_off' }));
    await user.click(screen.getByRole('button', { name: 'settings.skills.dormant.keep' }));

    expect(onDecide.mock.calls).toEqual([['switch_off'], ['keep']]);
  });

  it('keeps a busy answer focused and inert instead of disabling it', async () => {
    const { user, onDecide } = renderNotice([skill('notes')], true);
    const switchOff = screen.getByRole('button', { name: 'settings.skills.dormant.switch_off' });

    switchOff.focus();
    await user.keyboard('{Enter}');

    expect(switchOff).toHaveAttribute('aria-disabled', 'true');
    expect(switchOff).not.toBeDisabled();
    expect(switchOff).toHaveFocus();
    expect(onDecide).not.toHaveBeenCalled();
  });
});

/**
 * A skill card reads like an MCP server card (owner request 2026-10-21): the
 * skill above, its actions under a rule — and no rule where nothing follows it.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { SkillGallery } from '../SkillGallery';
import type { Skill } from '@/hooks/useSkills';

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
    skill_id: '33333333-3333-4333-8333-333333333333',
    ...over,
  };
}

const t = (key: string, options?: Record<string, string>) =>
  options?.name ? `${key}:${options.name}` : key;

function cardOf(name: string): HTMLElement {
  const card = screen
    .getByRole('button', { name: `settings.skills.gallery.open_details:${name}` })
    .closest<HTMLElement>('div.rounded-lg');
  if (!card) throw new Error(`no card for ${name}`);
  return card;
}

describe('SkillGallery card', () => {
  it('puts a personal skill’s actions under a rule, and shares from there', async () => {
    const onShare = vi.fn();
    const mine = skill();
    const { user } = renderWithProviders(
      <SkillGallery
        skills={[mine]}
        lng="en"
        t={t}
        onOpen={vi.fn()}
        onToggle={vi.fn()}
        toggling={false}
        onShare={onShare}
      />
    );

    const card = cardOf('my-skill');
    const [share] = within(card).getAllByRole('button', {
      name: 'settings.capability_share.action:my-skill',
    });
    const footer = share.closest('div.border-t');
    expect(footer, 'the actions sit under the card rule').not.toBeNull();
    // The switch and the details button stay above the rule.
    expect(footer).not.toContainElement(within(card).getByRole('switch'));
    await user.click(share);
    expect(onShare).toHaveBeenCalledExactlyOnceWith(mine);
  });

  it('draws no rule on a system skill, which has nothing under it', () => {
    renderWithProviders(
      <SkillGallery
        skills={[skill({ name: 'system-skill', scope: 'admin', skill_id: null })]}
        lng="en"
        t={t}
        onOpen={vi.fn()}
        onToggle={vi.fn()}
        toggling={false}
        onShare={vi.fn()}
      />
    );

    const card = cardOf('system-skill');
    expect(card.querySelector('.border-t')).toBeNull();
    expect(within(card).queryByRole('button', { name: /capability_share/ })).toBeNull();
    // One ground for every card: the fold tells a system skill apart.
    expect(card).toHaveClass('bg-card');
  });
});

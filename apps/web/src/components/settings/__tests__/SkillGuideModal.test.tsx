/**
 * SkillGuideModal — a documentation surface, so the contract worth pinning is
 * not business logic but the shell: it renders nothing while closed, exposes
 * its three tabs when open, actually swaps panels on tab navigation (Radix
 * unmounts the inactive ones), really renders the embedded tool catalogue
 * rather than an empty frame, and can be dismissed from the keyboard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { SkillGuideModal } from '../SkillGuideModal';

const I18N = 'settings.skills';
const TABS = {
  fundamentals: `${I18N}.guide_tab_fundamentals`,
  create: `${I18N}.guide_tab_create`,
  advanced: `${I18N}.guide_tab_advanced`,
};

function render(open = true, onOpenChange = vi.fn()) {
  const utils = renderWithProviders(
    <SkillGuideModal lng="en" open={open} onOpenChange={onOpenChange} />
  );
  return { ...utils, onOpenChange };
}

beforeEach(() => vi.clearAllMocks());

describe('SkillGuideModal — shell', () => {
  it('renders nothing while closed', () => {
    render(false);
    expect(screen.queryByText(`${I18N}.guide_modal_title`)).not.toBeInTheDocument();
  });

  it('opens on its three tabs, fundamentals first', async () => {
    render();
    expect(await screen.findByText(`${I18N}.guide_modal_title`)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: TABS.fundamentals })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByRole('tab', { name: TABS.create })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: TABS.advanced })).toBeInTheDocument();
  });
});

describe('SkillGuideModal — navigation & content', () => {
  it('swaps the active panel when another tab is selected', async () => {
    const { user } = render();
    await screen.findByText(`${I18N}.guide_modal_title`);
    const create = screen.getByRole('tab', { name: TABS.create });
    await user.click(create);
    expect(create).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: TABS.fundamentals })).toHaveAttribute(
      'aria-selected',
      'false'
    );
  });

  it('renders the embedded tool catalogue rather than an empty frame', async () => {
    const { user } = render();
    await screen.findByText(`${I18N}.guide_modal_title`);
    await user.click(screen.getByRole('tab', { name: TABS.advanced }));
    // The catalogue is a collapsed accordion of categories; expanding one must
    // reveal a real agent from TOOL_CATALOGUE rather than an empty panel.
    const category = await screen.findByRole('button', { name: /guide_cat_productivity/ });
    await user.click(category);
    expect(await screen.findByText('event_agent')).toBeInTheDocument();
    expect(await screen.findByText('get_events_tool')).toBeInTheDocument();
  });

  it('can be dismissed from the keyboard', async () => {
    const { user, onOpenChange } = render();
    await screen.findByText(`${I18N}.guide_modal_title`);
    await user.keyboard('{Escape}');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

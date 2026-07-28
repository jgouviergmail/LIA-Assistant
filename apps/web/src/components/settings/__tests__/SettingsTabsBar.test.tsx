/**
 * SettingsTabsBar — the persistent settings tab bar.
 *
 * Two things are worth pinning here, and neither is a class name:
 *
 *  1. the bar keeps working as a Radix tab list — every tab is announced with
 *     its role and selected state, and activating one drives the panel. A
 *     sticky wrapper that broke tab semantics would trade orientation for
 *     navigation;
 *  2. every tab keeps its icon and its label, and the label is allowed to
 *     shrink. The tabs share the row in equal parts at every width, so a long
 *     label (de/it/es) must be able to truncate INSIDE its button rather than
 *     escape it — which is what `whitespace-nowrap` without `min-w-0` did,
 *     clipping the text invisibly at the screen edge.
 */

import { describe, it, expect } from 'vitest';
import { Puzzle, Settings, Shield } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { SettingsTabsBar, type SettingsTabDescriptor } from '../SettingsTabsBar';

const THREE_TABS: SettingsTabDescriptor[] = [
  { value: 'preferences', label: 'Preferences', icon: Settings },
  { value: 'features', label: 'Features', icon: Puzzle },
  { value: 'administration', label: 'Administration', icon: Shield },
];

function renderBar(tabs: SettingsTabDescriptor[] = THREE_TABS, activeTab = 'preferences') {
  return renderWithProviders(
    <Tabs value={activeTab} onValueChange={() => {}}>
      <SettingsTabsBar tabs={tabs} />
      <TabsContent value="preferences">Preferences panel</TabsContent>
      <TabsContent value="features">Features panel</TabsContent>
      <TabsContent value="administration">Administration panel</TabsContent>
    </Tabs>
  );
}

describe('SettingsTabsBar', () => {
  it('renders one tab per descriptor, in order', () => {
    renderBar();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map(tab => tab.textContent)).toEqual(['Preferences', 'Features', 'Administration']);
  });

  it('marks the active tab as selected and shows its panel', () => {
    renderBar(THREE_TABS, 'features');
    expect(screen.getByRole('tab', { name: 'Features' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Preferences' })).toHaveAttribute(
      'aria-selected',
      'false'
    );
    expect(screen.getByText('Features panel')).toBeInTheDocument();
  });

  it('supports the two-tab layout non-superusers get', () => {
    renderBar(THREE_TABS.slice(0, 2));
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.queryByRole('tab', { name: 'Administration' })).not.toBeInTheDocument();
  });

  it('keeps every tab reachable and activatable by keyboard', async () => {
    const { user } = renderBar();
    const first = screen.getByRole('tab', { name: 'Preferences' });
    first.focus();
    // Radix tab lists move the roving focus with the arrow keys.
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Features' })).toHaveFocus();
  });

  it('hides the decorative icons from assistive technology', () => {
    const { container } = renderBar();
    const icons = container.querySelectorAll('[role="tab"] svg');
    expect(icons).toHaveLength(3);
    icons.forEach(icon => expect(icon).toHaveAttribute('aria-hidden', 'true'));
  });
});

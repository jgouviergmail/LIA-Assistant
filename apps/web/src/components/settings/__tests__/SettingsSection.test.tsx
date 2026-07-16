/**
 * SettingsSection — the static (non-collapsible) card layout and the collapsible
 * accordion layout.
 */

import { describe, it, expect } from 'vitest';
import { Star } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';
import { SettingsSection } from '../SettingsSection';

describe('SettingsSection — non-collapsible', () => {
  it('renders the title, description, icon and content always visible', () => {
    renderWithProviders(
      <SettingsSection
        value="s"
        title="My section"
        description="What it does"
        icon={Star}
        collapsible={false}
      >
        <p>Body content</p>
      </SettingsSection>
    );
    expect(screen.getByRole('heading', { name: 'My section' })).toBeInTheDocument();
    expect(screen.getByText('What it does')).toBeInTheDocument();
    expect(screen.getByText('Body content')).toBeInTheDocument();
  });
});

describe('SettingsSection — collapsible', () => {
  it('renders the title in an accordion trigger, collapsed by default', () => {
    renderWithProviders(
      <Accordion type="multiple">
        <SettingsSection value="s" title="Collapsible section">
          <p>Hidden body</p>
        </SettingsSection>
      </Accordion>
    );
    // Title is always in the trigger; the body is not visible until expanded.
    expect(screen.getByText('Collapsible section')).toBeInTheDocument();
    expect(screen.queryByText('Hidden body')).not.toBeInTheDocument();
  });

  it('reveals the content once the trigger is activated', async () => {
    const { user } = renderWithProviders(
      <Accordion type="multiple">
        <SettingsSection value="s" title="Collapsible section">
          <p>Hidden body</p>
        </SettingsSection>
      </Accordion>
    );
    await user.click(screen.getByRole('button', { name: /Collapsible section/ }));
    expect(screen.getByText('Hidden body')).toBeInTheDocument();
  });
});

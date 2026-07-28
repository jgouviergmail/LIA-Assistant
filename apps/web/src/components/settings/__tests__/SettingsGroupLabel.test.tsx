/**
 * SettingsGroupLabel — the label text, the optional leading icon, and the
 * heading level that makes the settings page navigable by structure.
 */

import { describe, it, expect } from 'vitest';
import { Star } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { SettingsGroupLabel } from '../SettingsGroupLabel';

describe('SettingsGroupLabel', () => {
  it('renders the label text', () => {
    renderWithProviders(<SettingsGroupLabel label="Preferences" />);
    expect(screen.getByText('Preferences')).toBeInTheDocument();
  });

  it('renders a leading icon when provided', () => {
    const { container } = renderWithProviders(
      <SettingsGroupLabel label="Preferences" icon={Star} />
    );
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('is a level-2 heading — the page goes h1 (title) → h2 (group) → h3 (section)', () => {
    renderWithProviders(<SettingsGroupLabel label="Preferences" />);
    expect(screen.getByRole('heading', { level: 2, name: 'Preferences' })).toBeInTheDocument();
  });

  it('hides its decorations from assistive technology', () => {
    const { container } = renderWithProviders(
      <SettingsGroupLabel label="Preferences" icon={Star} />
    );
    // Neither the icon nor the divider rule carries information the label lacks.
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByRole('heading', { level: 2 }).nextElementSibling).toHaveAttribute(
      'aria-hidden',
      'true'
    );
  });
});

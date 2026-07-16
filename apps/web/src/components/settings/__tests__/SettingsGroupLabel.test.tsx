/**
 * SettingsGroupLabel — the label text and optional leading icon.
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
});

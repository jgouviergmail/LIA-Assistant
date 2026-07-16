/**
 * StatusBadge / StatusDot — status→label/icon/colour mapping and the icon toggle.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { StatusBadge, StatusDot } from '../status-badge';

describe('StatusBadge', () => {
  it('capitalises the status as its default label', () => {
    renderWithProviders(<StatusBadge status="granted" />);
    expect(screen.getByText('Granted')).toBeInTheDocument();
  });

  it('uses a custom label when provided (i18n path)', () => {
    renderWithProviders(<StatusBadge status="denied" label="Blocked" />);
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(screen.queryByText('Denied')).not.toBeInTheDocument();
  });

  it('renders a status icon by default and omits it when showIcon is false', () => {
    const { container, rerender } = renderWithProviders(<StatusBadge status="warning" />);
    expect(container.querySelector('svg')).not.toBeNull();
    rerender(<StatusBadge status="warning" showIcon={false} />);
    expect(container.querySelector('svg')).toBeNull();
  });
});

describe('StatusDot', () => {
  it('exposes a status role with the status as its accessible name and colour', () => {
    renderWithProviders(<StatusDot status="granted" />);
    const dot = screen.getByRole('status', { name: 'granted' });
    expect(dot.className).toContain('bg-green-500');
  });

  it('prefers an explicit title for the accessible name', () => {
    renderWithProviders(<StatusDot status="denied" title="Access denied" />);
    expect(screen.getByRole('status', { name: 'Access denied' })).toBeInTheDocument();
  });
});

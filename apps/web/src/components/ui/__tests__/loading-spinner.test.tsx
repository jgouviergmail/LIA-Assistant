/**
 * LoadingSpinner — the status role, screen-reader label and variant styling.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { LoadingSpinner } from '../loading-spinner';

describe('LoadingSpinner', () => {
  it('exposes a status role labelled "Loading..." by default', () => {
    renderWithProviders(<LoadingSpinner />);
    expect(screen.getByRole('status', { name: 'Loading...' })).toBeInTheDocument();
  });

  it('accepts a custom screen-reader label', () => {
    renderWithProviders(<LoadingSpinner label="Fetching results" />);
    expect(screen.getByRole('status', { name: 'Fetching results' })).toBeInTheDocument();
  });

  it('maps size and colour variants to distinct styling', () => {
    const { rerender } = renderWithProviders(<LoadingSpinner size="sm" />);
    const small = screen.getByRole('status').getAttribute('class');
    rerender(<LoadingSpinner size="2xl" spinnerColor="destructive" />);
    expect(screen.getByRole('status').getAttribute('class')).not.toBe(small);
  });
});

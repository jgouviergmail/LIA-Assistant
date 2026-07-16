/**
 * Badge — children, optional icon/pulse decorations and variant styling.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Badge } from '../badge';

describe('Badge', () => {
  it('renders its children', () => {
    renderWithProviders(<Badge>New</Badge>);
    expect(screen.getByText('New')).toBeInTheDocument();
  });

  it('renders a leading icon when provided', () => {
    renderWithProviders(<Badge icon={<span data-testid="dot" />}>Live</Badge>);
    expect(screen.getByTestId('dot')).toBeInTheDocument();
  });

  it('renders the pulse indicator only when pulse is set', () => {
    const { container, rerender } = renderWithProviders(<Badge>Idle</Badge>);
    expect(container.querySelector('.animate-ping')).toBeNull();
    rerender(<Badge pulse>Idle</Badge>);
    expect(container.querySelector('.animate-ping')).not.toBeNull();
  });

  it('maps the variant prop to distinct styling (default vs success)', () => {
    const { rerender } = renderWithProviders(<Badge variant="default">X</Badge>);
    const def = screen.getByText('X').className;
    rerender(<Badge variant="success">X</Badge>);
    expect(screen.getByText('X').className).not.toBe(def);
  });
});

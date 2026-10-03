/**
 * The application wears the landing's background: the same cosmic layers and
 * the same attention canvas, under the `.cosmos` token scope, decorative.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../AttentionBackdrop', () => ({
  AttentionBackdrop: () => <div data-testid="attention-backdrop" />,
}));

import { AppCosmos } from '../AppCosmos';

afterEach(() => {
  cleanup();
});

describe('AppCosmos', () => {
  it("renders the landing's layers inside a decorative cosmos scope", () => {
    render(<AppCosmos />);

    const scope = screen.getByTestId('app-cosmos');
    expect(scope).toHaveClass('cosmos');
    expect(scope).toHaveAttribute('aria-hidden', 'true');
    expect(scope).toContainElement(screen.getByTestId('cosmic-backdrop'));
    expect(scope).toContainElement(screen.getByTestId('attention-backdrop'));
  });
});

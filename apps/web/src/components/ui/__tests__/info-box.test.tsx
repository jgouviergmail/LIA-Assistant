/**
 * InfoBox — content passthrough and variant styling.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { InfoBox } from '../info-box';

describe('InfoBox', () => {
  it('renders arbitrary children', () => {
    renderWithProviders(
      <InfoBox>
        <p>Body copy</p>
      </InfoBox>
    );
    expect(screen.getByText('Body copy')).toBeInTheDocument();
  });

  it('maps the variant prop to distinct styling (default vs warning)', () => {
    const { rerender } = renderWithProviders(<InfoBox>x</InfoBox>);
    const def = screen.getByText('x').className;
    rerender(<InfoBox variant="warning">x</InfoBox>);
    expect(screen.getByText('x').className).not.toBe(def);
  });

  it('forwards arbitrary HTML attributes to the container', () => {
    renderWithProviders(<InfoBox data-testid="box" role="note" />);
    expect(screen.getByTestId('box')).toHaveAttribute('role', 'note');
  });
});

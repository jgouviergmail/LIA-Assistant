/**
 * The civil-day frame of meetings, calls and SMS. Its ground follows its host:
 * on the page it is a card; inside a card-coloured fold (an SMS sender's) it
 * takes the background, so the two still alternate (owner rule 2026-10-21).
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { TimelineDayGroup } from '../timeline-group';

function frameOf(text: string): HTMLElement | null {
  return screen.getByText(text).parentElement;
}

describe('TimelineDayGroup', () => {
  it('is a named day section on the card ground by default', () => {
    renderWithProviders(
      <TimelineDayGroup
        headingId="day-1"
        heading="Mardi 21 octobre"
        level={2}
        dayNumber="21"
        month="oct."
      >
        <p>contenu</p>
      </TimelineDayGroup>
    );

    expect(screen.getByRole('region', { name: 'Mardi 21 octobre' })).toBeInTheDocument();
    expect(frameOf('contenu')).toHaveClass('bg-card');
  });

  it('takes the background inside a card-coloured host', () => {
    renderWithProviders(
      <TimelineDayGroup
        headingId="day-2"
        heading="Mercredi 22 octobre"
        level={2}
        dayNumber="22"
        month="oct."
        surface="background"
      >
        <p>contenu</p>
      </TimelineDayGroup>
    );

    expect(frameOf('contenu')).toHaveClass('bg-background');
    expect(frameOf('contenu')).not.toHaveClass('bg-card');
  });
});

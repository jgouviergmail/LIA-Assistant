/**
 * MissionPicker — the /demo entry point.
 *
 * Six cards, one per mission, above which one sentence tells the visitor what
 * they are looking at. That sentence is centred (owner request 2026-08-07):
 * the grid below it is centred content, and a left-aligned lead-in above a
 * centred block reads as a stray paragraph.
 *
 * Untested until now, which is why the layout request is the occasion to pin
 * what the picker actually owes: one real button per mission, each carrying
 * its title, tagline and mechanism, and reporting the id it was given.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MissionPicker } from '../MissionPicker';
import { SHOWROOM_MISSIONS } from '../missions';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function setup() {
  const onSelect = vi.fn();
  const utils = render(<MissionPicker missions={SHOWROOM_MISSIONS} onSelect={onSelect} />);
  return { ...utils, onSelect, user: userEvent.setup() };
}

describe('MissionPicker — the lead-in', () => {
  it('centres the sentence above the grid', () => {
    setup();

    expect(screen.getByText('showroom.picker.subtitle').className).toContain('text-center');
  });
});

describe('MissionPicker — the cards', () => {
  it('offers one card per mission', () => {
    setup();

    const list = screen.getByRole('list');

    expect(within(list).getAllByRole('listitem')).toHaveLength(SHOWROOM_MISSIONS.length);
  });

  it('makes each card a real button, so keyboard and screen reader get it free', () => {
    setup();

    for (const mission of SHOWROOM_MISSIONS) {
      const card = screen.getByTestId(`showroom-pick-${mission.id}`);
      expect(card.tagName).toBe('BUTTON');
      expect(card).toHaveAttribute('type', 'button');
    }
  });

  it('states title, tagline and mechanism on every card', () => {
    setup();

    for (const mission of SHOWROOM_MISSIONS) {
      const card = screen.getByTestId(`showroom-pick-${mission.id}`);
      expect(card.textContent).toContain(mission.titleKey);
      expect(card.textContent).toContain(mission.taglineKey);
      expect(card.textContent).toContain(mission.mechanismKey);
    }
  });

  it('reports the mission the visitor chose', async () => {
    const { onSelect, user } = setup();
    const chosen = SHOWROOM_MISSIONS[1];

    await user.click(screen.getByTestId(`showroom-pick-${chosen.id}`));

    expect(onSelect).toHaveBeenCalledWith(chosen.id);
  });

  it('renders nothing but the lead-in when no mission is offered', () => {
    // Defensive: the mission registry is code, but an empty list must not
    // throw — it renders an empty list, not a broken page.
    render(<MissionPicker missions={[]} onSelect={vi.fn()} />);

    expect(within(screen.getByRole('list')).queryAllByRole('listitem')).toHaveLength(0);
  });
});

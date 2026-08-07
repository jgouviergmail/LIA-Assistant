/**
 * HonestyStrip — the showroom's contract with the visitor.
 *
 * Three statements that must never leave the screen: guided demonstration,
 * synthetic data, no external action. Rendered on the mission picker AND in
 * every mission header, so a visitor never reads showroom content without
 * them.
 *
 * Owner request 2026-08-07: the mission intro was "trop condensé et peu
 * lisible" — the three statements ran together in one grey line under the
 * title, wrapping mid-sentence on a phone. They now sit in a panel of their
 * own with real leading, and each statement is a list item so a screen reader
 * announces three facts rather than one run-on sentence.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { HonestyStrip } from '../HonestyStrip';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const STATEMENTS = [
  'showroom.honesty.guided',
  'showroom.honesty.synthetic',
  'showroom.honesty.no_external',
];

describe('HonestyStrip', () => {
  it('always states the three facts', () => {
    render(<HonestyStrip />);

    for (const key of STATEMENTS) expect(screen.getByText(key)).toBeInTheDocument();
  });

  it('exposes them as a list, so they are announced as three separate facts', () => {
    render(<HonestyStrip />);

    const list = screen.getByRole('list');

    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
  });

  it('carries a programmatic name, since it is a region of its own', () => {
    render(<HonestyStrip />);

    expect(screen.getByRole('list')).toHaveAccessibleName('showroom.honesty.title');
  });

  it('sits in its own panel rather than floating under the title', () => {
    const { container } = render(<HonestyStrip />);

    const panel = container.firstElementChild as HTMLElement;

    expect(panel.className).toContain('rounded-xl');
    expect(panel.className).toContain('border');
  });

  it('separates the statements without a bare punctuation glyph on phones', () => {
    // The `·` was decoration between wrapped fragments; a stacked list needs
    // no separator, and a screen reader never had to hear it.
    const { container } = render(<HonestyStrip />);

    expect(container.textContent).not.toContain('·');
  });
});

/**
 * RegistersPage — two registers, two tabs, never one merged list (ADR-263).
 *
 * The owner's arbitration made concrete: the registers count different things
 * (one row per ACTION against one row per CONSULTATION) and a reader able to
 * add their totals would get a number that means nothing. The oracles here are
 * the ones that would break if someone "simplified" the page back into a
 * single list with a filter.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { RegistersPage } from '@/components/effects/RegistersPage';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const dictionary: Record<string, string> = {
        'registers.title': 'Transparency registers',
        'registers.description': 'Two separate lists',
        'registers.tab_actions': 'Actions',
        'registers.tab_consultations': 'Consultations',
      };
      return dictionary[key] ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

// The seal card fetches on mount. It has its own suite; leaving it real here
// would make this file's oracles depend on a request it never talks about.
vi.mock('@/components/effects/ChainSealCard', () => ({
  ChainSealCard: () => <div data-testid="chain-seal" />,
}));

vi.mock('@/components/effects/EffectsJournal', () => ({
  EffectsJournal: () => <div data-testid="actions-register">actions</div>,
}));

vi.mock('@/components/effects/TreatmentsJournal', () => ({
  TreatmentsJournal: () => <div data-testid="consultations-register">consultations</div>,
}));

describe('RegistersPage', () => {
  it('names the page once, at the top', () => {
    render(<RegistersPage lng="en" />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'Transparency registers' })
    ).toBeInTheDocument();
  });

  it('offers the two registers as two tabs', () => {
    render(<RegistersPage lng="en" />);

    expect(screen.getByRole('tab', { name: /Actions/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Consultations/ })).toBeInTheDocument();
  });

  it('opens on the action register', () => {
    render(<RegistersPage lng="en" />);

    expect(screen.getByRole('tab', { name: /Actions/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('actions-register')).toBeInTheDocument();
  });

  it('shows the consultation register when its tab is chosen', async () => {
    render(<RegistersPage lng="en" />);

    await userEvent.click(screen.getByRole('tab', { name: /Consultations/ }));

    expect(screen.getByTestId('consultations-register')).toBeInTheDocument();
  });

  it('never shows the two registers as one list', () => {
    render(<RegistersPage lng="en" />);

    expect(screen.queryByTestId('consultations-register')).not.toBeInTheDocument();
  });

  it('reaches the tabs from the keyboard', async () => {
    render(<RegistersPage lng="en" />);
    const actions = screen.getByRole('tab', { name: /Actions/ });

    actions.focus();
    await userEvent.keyboard('{ArrowRight}');

    expect(screen.getByRole('tab', { name: /Consultations/ })).toHaveFocus();
  });
});

describe('RegistersPage — what the registers can PROVE (ADR-263, lot 5)', () => {
  it('states the sealing ABOVE both tabs, once', () => {
    // One chain seals the two journals. Two indicators would invite a reader to
    // believe each register was checked separately.
    render(<RegistersPage lng="en" />);

    expect(screen.getAllByTestId('chain-seal')).toHaveLength(1);
  });

  it('shows the sealing whichever register is open', async () => {
    render(<RegistersPage lng="en" />);
    await userEvent.click(screen.getByRole('tab', { name: /Consultations/ }));

    expect(screen.getByTestId('chain-seal')).toBeInTheDocument();
  });
});

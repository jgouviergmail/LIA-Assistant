/**
 * A fourth READING of the two registers, never a fourth register.
 *
 * ADR-263 settled that an ACTION and a CONSULTATION are different objects and
 * must not share one list. An initiative is neither — it is an ORIGIN, and it
 * holds both kinds. So the oracles here are: the two registers stay separate
 * inside the tab, both read `initiative`, and nothing that belongs to the
 * person moves out of the two lists where their owner has always found it.
 *
 * Why it deserved its own tab, measured on production over fourteen days: 319
 * heartbeat runs against 22 conversational turns. Merged, the lines a person
 * actually cares about would be unreadable.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { InitiativeJournal } from '@/components/effects/InitiativeJournal';
import { RegistersPage } from '@/components/effects/RegistersPage';

const DICTIONARY: Record<string, string> = {
  'registers.title': 'Transparency registers',
  'registers.description': 'Two separate lists',
  'registers.tab_actions': 'Actions',
  'registers.tab_consultations': 'Consultations',
  'registers.tab_initiative': "LIA's own initiative",
  'registers.tab_overview': 'Overview',
  'registers.initiative_description': 'What LIA did without being asked',
  'registers.initiative_actions': 'Actions taken on its own',
  'registers.initiative_consultations': 'Sources consulted on its own',
  'registers.initiative_actions_description': 'What it did on its own',
  'registers.initiative_consultations_description': 'What it opened on its own',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => DICTIONARY[key] ?? key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('@/components/effects/ChainSealCard', () => ({
  ChainSealCard: () => <div data-testid="chain-seal" />,
}));

vi.mock('@/components/effects/RegisterCharts', () => ({
  RegisterCharts: () => <div data-testid="charts" />,
}));

type JournalMockProps = { origin?: string; heading?: { title: string; description: string } };

/** The real journals render their OWN header; the mocks echo what they were
 *  handed, so the test can tell a heading passed down from one stacked on top. */
vi.mock('@/components/effects/EffectsJournal', () => ({
  EffectsJournal: ({ origin, heading }: JournalMockProps) => (
    <section data-testid="actions-register" data-origin={origin ?? 'all'}>
      {heading ? <h2>{heading.title}</h2> : null}
      {heading ? <p>{heading.description}</p> : null}
    </section>
  ),
}));

vi.mock('@/components/effects/TreatmentsJournal', () => ({
  TreatmentsJournal: ({ origin, heading }: JournalMockProps) => (
    <section data-testid="consultations-register" data-origin={origin ?? 'all'}>
      {heading ? <h2>{heading.title}</h2> : null}
      {heading ? <p>{heading.description}</p> : null}
    </section>
  ),
}));

describe('InitiativeJournal', () => {
  it('keeps the two registers separate inside the reading', () => {
    render(<InitiativeJournal lng="en" />);

    expect(screen.getByTestId('actions-register')).toBeInTheDocument();
    expect(screen.getByTestId('consultations-register')).toBeInTheDocument();
  });

  it('reads both registers under the initiative authorship', () => {
    render(<InitiativeJournal lng="en" />);

    expect(screen.getByTestId('actions-register')).toHaveAttribute('data-origin', 'initiative');
    expect(screen.getByTestId('consultations-register')).toHaveAttribute(
      'data-origin',
      'initiative'
    );
  });

  it('gives each register the wording of THIS tab', () => {
    // Two stacked lists with no headings would read as one undifferentiated
    // column to a screen reader — the charter's grouping rule applied here.
    render(<InitiativeJournal lng="en" />);

    expect(
      screen.getByRole('heading', { level: 2, name: 'Actions taken on its own' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: 'Sources consulted on its own' })
    ).toBeInTheDocument();
  });

  it('gives each list ONE heading rather than two stacked titles', () => {
    // Reported from the dev instance, 2026-09-07: every list carried two
    // titles — « Actions menées d'elle-même » above « Journal des actions » —
    // because the wording was stacked on top of a journal that names itself.
    // Handing it DOWN is what makes one heading structural rather than watched.
    render(<InitiativeJournal lng="en" />);

    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
  });

  it('describes each list under its own title', () => {
    render(<InitiativeJournal lng="en" />);

    expect(screen.getByText('What it did on its own')).toBeInTheDocument();
    expect(screen.getByText('What it opened on its own')).toBeInTheDocument();
  });

  it('says in words what the reading holds and what it does not', () => {
    render(<InitiativeJournal lng="en" />);

    expect(screen.getByText('What LIA did without being asked')).toBeInTheDocument();
  });
});

describe('RegistersPage — the initiative tab', () => {
  it('offers it beside the two registers', () => {
    render(<RegistersPage lng="en" />);

    expect(screen.getByRole('tab', { name: /LIA's own initiative/ })).toBeInTheDocument();
  });

  it('leaves the two first tabs reading what the person set in motion', () => {
    // The property that stops the change from being a regression: a routine
    // the person configured is THEIR instruction, and its rows must not
    // silently move into a tab they never opened.
    render(<RegistersPage lng="en" />);

    expect(screen.getByTestId('actions-register')).toHaveAttribute('data-origin', 'mine');
  });

  it('shows the initiative reading only once its tab is selected', async () => {
    const user = userEvent.setup();
    render(<RegistersPage lng="en" />);

    await user.click(screen.getByRole('tab', { name: /LIA's own initiative/ }));

    expect(screen.getByText('What LIA did without being asked')).toBeInTheDocument();
  });

  it('is reachable with the keyboard like every other tab', async () => {
    const user = userEvent.setup();
    render(<RegistersPage lng="en" />);

    await user.click(screen.getByRole('tab', { name: 'Actions' }));
    await user.keyboard('{ArrowRight}{ArrowRight}');

    expect(screen.getByRole('tab', { name: /LIA's own initiative/ })).toHaveFocus();
  });
});

describe('RegistersPage — the fourth tab costs nothing until it is opened', () => {
  it('does not mount the initiative registers on page open', () => {
    // The page's own promise: "opening the page costs one request, not two".
    // A fourth tab rendered eagerly would have made it four — two of them for
    // a reading nobody asked to see. Radix unmounts inactive content, and this
    // is the oracle that keeps it true.
    render(<RegistersPage lng="en" />);

    expect(screen.getAllByTestId('actions-register')).toHaveLength(1);
    expect(screen.queryByText('What LIA did without being asked')).not.toBeInTheDocument();
  });

  it('mounts exactly one action register at a time', async () => {
    const user = userEvent.setup();
    render(<RegistersPage lng="en" />);

    await user.click(screen.getByRole('tab', { name: /LIA's own initiative/ }));

    // The initiative reading mounts its own pair; the "mine" one is gone.
    const registers = screen.getAllByTestId('actions-register');
    expect(registers).toHaveLength(1);
    expect(registers[0]).toHaveAttribute('data-origin', 'initiative');
  });
});

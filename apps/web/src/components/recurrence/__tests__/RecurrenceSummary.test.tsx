/**
 * What the reader is told a recurrence will do, before saving it.
 *
 * The i18n stub renders the KEY, so every assertion here reads a key, never a
 * French label.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { RecurrenceSpec } from '@/hooks/useScheduledActions';
import { emptyRecurrence } from '@/lib/recurrence';
import { RecurrenceSummary } from '../RecurrenceSummary';

function spec(over: Partial<RecurrenceSpec> = {}): RecurrenceSpec {
  return { ...emptyRecurrence('2026-09-07'), ...over };
}

describe('RecurrenceSummary', () => {
  it('states the per-day count as an UPPER BOUND, never an exact number', () => {
    // A clock change makes the real count differ on one day a year: 24
    // declared, 23 served in spring (measured server-side).
    render(
      <RecurrenceSummary
        spec={spec({
          times: {
            mode: 'every',
            step_minutes: 120,
            start: { hour: 8, minute: 0 },
            end: { hour: 14, minute: 0 },
          },
        })}
        locale="fr-FR"
        timezone="Europe/Paris"
      />
    );
    expect(screen.getByTestId('recurrence-per-day')).toHaveTextContent('recurrence.summary_per_day');
  });

  it('lists the moments a served day fires at', () => {
    render(
      <RecurrenceSummary
        spec={spec({
          times: {
            mode: 'at',
            at: [
              { hour: 8, minute: 0 },
              { hour: 19, minute: 30 },
            ],
          },
        })}
        locale="fr-FR"
        timezone="Europe/Paris"
      />
    );
    const times = screen.getByTestId('recurrence-times');
    expect(times).toHaveTextContent('08:00');
    expect(times).toHaveTextContent('19:30');
  });

  it('renders the sentence the SERVER composed, never one of its own', () => {
    // The wording is the server's: composing a second one here would be a
    // second authority on the same fact, and the two would drift.
    render(
      <RecurrenceSummary
        spec={spec()}
        locale="fr-FR"
        timezone="Europe/Paris"
        sentence="Tous les jours à 08:00"
      />
    );
    expect(screen.getByTestId('recurrence-sentence')).toHaveTextContent('Tous les jours à 08:00');
  });

  it('shows no sentence block at all when the server has not composed one', () => {
    render(<RecurrenceSummary spec={spec()} locale="fr-FR" timezone="Europe/Paris" />);
    expect(screen.queryByTestId('recurrence-sentence')).not.toBeInTheDocument();
  });

  it('renders the next real dates when the server supplied them', () => {
    render(
      <RecurrenceSummary
        spec={spec()}
        locale="fr-FR"
        timezone="Europe/Paris"
        occurrences={['2026-09-08T06:00:00Z', '2026-09-09T06:00:00Z']}
      />
    );
    const list = screen.getByTestId('recurrence-occurrences');
    expect(list.querySelectorAll('li')).toHaveLength(2);
    // A `<time>` carries the machine-readable instant beside the local label.
    expect(list.querySelector('time')).toHaveAttribute('dateTime', '2026-09-08T06:00:00Z');
  });

  it('says the series is over rather than showing an empty list', () => {
    render(
      <RecurrenceSummary
        spec={spec()}
        locale="fr-FR"
        timezone="Europe/Paris"
        occurrences={[]}
        finished
      />
    );
    expect(screen.getByText('recurrence.summary_finished')).toBeInTheDocument();
    expect(screen.queryByTestId('recurrence-occurrences')).not.toBeInTheDocument();
  });

  it('drops an unparseable instant instead of rendering Invalid Date', () => {
    render(
      <RecurrenceSummary
        spec={spec()}
        locale="fr-FR"
        timezone="Europe/Paris"
        occurrences={['not-a-date', '2026-09-08T06:00:00Z']}
      />
    );
    expect(screen.getByTestId('recurrence-occurrences').querySelectorAll('li')).toHaveLength(1);
  });

  it('never renders the epoch when an instant is null', () => {
    // `new Date(null)` is 1970-01-01 and `isNaN` is false: a naive filter lets
    // it through, and a finished series announced "01/01/1970".
    render(
      <RecurrenceSummary
        spec={spec()}
        locale="fr-FR"
        timezone="Europe/Paris"
        occurrences={[null as unknown as string]}
      />
    );
    expect(screen.queryByTestId('recurrence-occurrences')).not.toBeInTheDocument();
  });
});

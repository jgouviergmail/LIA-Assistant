/**
 * ScheduledActionsList — what the hub says about each routine's next run.
 *
 * A condition routine has no next run to announce (ADR-322): its trigger is the
 * system's next CHECK, minutes away, and « next run at 14:40 » would promise a
 * run that only happens if the awaited fact does. Its sentence — « checked
 * about every 10 min » — already says what there is to say.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

import { ScheduledActionsList, type ScheduledActionRow } from '../ScheduledActionsList';

function row(over: Partial<ScheduledActionRow> = {}): ScheduledActionRow {
  return {
    id: 'r1',
    title: 'Morning brief',
    is_enabled: true,
    trigger_kind: 'time',
    next_trigger_at: '2026-09-26T06:00:00Z',
    schedule_display: 'Every day at 08:00',
    ...over,
  };
}

describe('ScheduledActionsList', () => {
  it('announces the next run of a scheduled routine', () => {
    render(<ScheduledActionsList actions={[row()]} locale="en-GB" />);

    expect(screen.getByText('notifications_hub.next_run')).toBeInTheDocument();
  });

  it('announces no run for a condition routine, only its check cadence', () => {
    render(
      <ScheduledActionsList
        actions={[
          row({
            trigger_kind: 'condition',
            next_trigger_at: '2026-09-25T12:10:00Z',
            schedule_display: 'Checked about every 10 min',
          }),
        ]}
        locale="en-GB"
      />
    );

    expect(screen.getByText('Checked about every 10 min')).toBeInTheDocument();
    expect(screen.queryByText('notifications_hub.next_run')).not.toBeInTheDocument();
    expect(screen.queryByText('notifications_hub.next_run_unknown')).not.toBeInTheDocument();
  });
});

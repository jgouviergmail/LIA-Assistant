/**
 * Tasks card (P15 extension) — strictly pending/overdue tasks.
 *
 * Rows open the chat with a direction-aware intent: reschedule for overdue,
 * progress for pending (QW-9 `?draft=` pattern).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { TasksCard } from '../cards/TasksCard';
import type { CardSection, TasksData } from '@/types/briefing';

const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

function section(data: TasksData | null, status = 'ok'): CardSection<TasksData> {
  return {
    status: status as CardSection<TasksData>['status'],
    data,
    generated_at: '2026-07-22T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const cardProps = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };

const fullData: TasksData = {
  items: [
    {
      title: 'Payer la facture EDF',
      due_date_iso: '2026-07-20',
      days_until_due: -2,
      overdue: true,
    },
    { title: 'Préparer le dossier', due_date_iso: '2026-07-22', days_until_due: 0, overdue: false },
    { title: 'Relancer Paul', due_date_iso: null, days_until_due: null, overdue: false },
  ],
  overdue_count: 1,
};

describe('TasksCard', () => {
  beforeEach(() => {
    push.mockClear();
  });

  it('renders overdue tasks with reschedule intent and overdue badge', () => {
    render(<TasksCard {...cardProps} section={section(fullData)} />);

    const overdue = screen.getByRole('button', {
      name: /intents\.task_reschedule\|subject=Payer la facture EDF/,
    });
    fireEvent.click(overdue);
    expect(push).toHaveBeenCalledWith(expect.stringContaining('/fr/dashboard/chat?draft='));
    expect(push.mock.calls[0][0]).toContain(encodeURIComponent('Payer la facture EDF'));
    expect(
      screen.getByText('dashboard.briefing.cards.tasks.overdue_days|count=2')
    ).toBeInTheDocument();
  });

  it('renders pending tasks with progress intent and due-today badge', () => {
    render(<TasksCard {...cardProps} section={section(fullData)} />);

    expect(
      screen.getByRole('button', {
        name: /intents\.task_progress\|subject=Préparer le dossier/,
      })
    ).toBeInTheDocument();
    expect(screen.getByText('dashboard.briefing.cards.tasks.due_today')).toBeInTheDocument();
  });

  it('renders undated tasks without a due badge', () => {
    render(<TasksCard {...cardProps} section={section(fullData)} />);

    const undated = screen.getByRole('button', {
      name: /intents\.task_progress\|subject=Relancer Paul/,
    });
    expect(undated).toBeInTheDocument();
    expect(
      screen.queryByText(/dashboard\.briefing\.cards\.tasks\.due_in_days/)
    ).not.toBeInTheDocument();
  });

  it('shows the empty state when the section is empty', () => {
    render(<TasksCard {...cardProps} section={section(null, 'empty')} />);
    expect(screen.getByText('dashboard.briefing.cards.tasks.empty')).toBeInTheDocument();
  });

  it('is hidden entirely when the section is not configured', () => {
    const { container } = render(
      <TasksCard {...cardProps} section={section(null, 'not_configured')} />
    );
    expect(container.firstChild).toBeNull();
  });
});

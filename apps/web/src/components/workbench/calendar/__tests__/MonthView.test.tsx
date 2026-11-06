/**
 * The month grid (ADR-369, Task 5b.1).
 *
 * Six weeks from the locale's first weekday; an event is a bar across the
 * days it touches; a day past the lane budget says how many more it holds and
 * opens in the agenda; the days are walked with the arrows, Home and End.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { ShownEvent } from '@/lib/workbench/calendar/events';
import { monthGrid } from '@/lib/workbench/calendar/layout';

vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/calendar',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { MonthView } from '../MonthView';

const PARIS = 'Europe/Paris';

function event(key: string, overrides: Partial<ShownEvent>): ShownEvent {
  return {
    id: key,
    key: `primary|${key}`,
    calendar_id: 'primary',
    summary: key,
    all_day: true,
    start: '2026-10-27',
    end: '2026-10-28',
    location: null,
    recurring: false,
    conference_url: null,
    color: '#7c3aed',
    ...overrides,
  };
}

function month(events: ShownEvent[], firstDay = 1) {
  const days = monthGrid('2026-10-15', firstDay);
  return renderWithProviders(
    <MonthView
      lng="en"
      days={days}
      month="2026-10"
      today="2026-10-28"
      zone={PARIS}
      events={events}
      openId={null}
      hrefOf={item => `/event/${item.id}`}
      agendaHref={day => `/agenda/${day}`}
      linkRef={() => undefined}
    />
  );
}

describe('MonthView', () => {
  it('draws six weeks, the days of other months as well', () => {
    month([]);

    expect(screen.getAllByRole('row')).toHaveLength(7);
    expect(screen.getAllByRole('gridcell')).toHaveLength(42);
  });

  it('draws an event as one bar across the days it touches, from the cell it starts in', () => {
    month([event('Trip', { start: '2026-10-27', end: '2026-10-30' })]);

    const bar = screen.getByRole('link', { name: 'Trip' });
    expect(bar.parentElement?.getAttribute('style')).toContain('width: calc(300% - 4px)');
    const cell = bar.closest('[role="gridcell"]');
    expect(cell?.querySelector('a')?.getAttribute('href')).toBe('/agenda/2026-10-27');
  });

  it('counts a crowded day’s rest, a link to that day in the agenda', () => {
    month(['a', 'b', 'c', 'd'].map(key => event(key, {})));

    const more = screen.getByRole('link', { name: 'workbench.calendar.more_label' });
    expect(more.getAttribute('href')).toBe('/agenda/2026-10-27');
    expect(screen.getAllByRole('link', { name: /^[abcd]$/ })).toHaveLength(2);
  });

  it('walks the days with the arrows, Home and End, one day in the tab order', async () => {
    const { user } = month([]);
    const days = screen
      .getAllByRole('gridcell')
      .map(cell => cell.querySelector('a'))
      .filter((link): link is HTMLAnchorElement => link instanceof HTMLAnchorElement);
    const today = days.find(link => link.tabIndex === 0);
    expect(today?.getAttribute('href')).toBe('/agenda/2026-10-28');
    expect(days.filter(link => link.tabIndex === 0)).toHaveLength(1);

    today?.focus();
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement?.getAttribute('href')).toBe('/agenda/2026-10-29');
    await user.keyboard('{ArrowDown}');
    expect(document.activeElement?.getAttribute('href')).toBe('/agenda/2026-11-05');
    await user.keyboard('{Home}');
    expect(document.activeElement?.getAttribute('href')).toBe('/agenda/2026-11-02');
    await user.keyboard('{End}');
    expect(document.activeElement?.getAttribute('href')).toBe('/agenda/2026-11-08');
  });
});

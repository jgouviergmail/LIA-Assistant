/**
 * The agenda (ADR-369, mock-up « Agenda ») — the calendar's view on a phone.
 *
 * Only the days holding something, each day's all-day events first, then its
 * timed ones on the account's wall; an event across midnight shows on each
 * day it touches and says it goes on; the open event is marked; the day a
 * « +N » points at is scrolled to inside the list, never by moving the page.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { ShownEvent } from '@/lib/workbench/calendar/events';

vi.mock('next/navigation', () => ({
  usePathname: () => '/fr/dashboard/tools/calendar',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AgendaView } from '../AgendaView';

// Paris is UTC+1 after 2026-10-25 (the end of summer time).
const PARIS = 'Europe/Paris';
const DAYS = ['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29'];

function event(key: string, overrides: Partial<ShownEvent>): ShownEvent {
  return {
    id: key,
    key: `primary|${key}`,
    calendar_id: 'primary',
    summary: key,
    all_day: false,
    start: '2026-10-27T08:00:00Z',
    end: '2026-10-27T09:00:00Z',
    location: null,
    recurring: false,
    conference_url: null,
    color: '#7c3aed',
    ...overrides,
  };
}

function agenda(
  events: ShownEvent[],
  { openId = null, focusDay = null }: { openId?: string | null; focusDay?: string | null } = {}
) {
  const linkRef = vi.fn();
  const rendered = renderWithProviders(
    <AgendaView
      lng="fr"
      days={DAYS}
      today="2026-10-28"
      zone={PARIS}
      events={events}
      openId={openId}
      focusDay={focusDay}
      hrefOf={item => `/event/${item.id}`}
      linkRef={linkRef}
    />
  );
  return { ...rendered, linkRef };
}

/** Each entry of a day, as « times · title ». */
function entriesOf(heading: string): string[] {
  const day = screen.getByRole('region', { name: heading });
  return within(day)
    .getAllByRole('link')
    .map(link => {
      const times = link.firstElementChild?.textContent;
      const title = link.querySelector('.font-medium')?.textContent;
      return `${times} · ${title}`;
    });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AgendaView', () => {
  it('lists only the days holding something, all-day events first, then by start', () => {
    agenda([
      event('standup', { start: '2026-10-27T08:00:00Z', end: '2026-10-27T08:15:00Z' }),
      event('lunch', { start: '2026-10-27T11:30:00Z', end: '2026-10-27T12:30:00Z' }),
      event('holiday', { all_day: true, start: '2026-10-27', end: '2026-10-29' }),
    ]);

    expect(screen.getAllByRole('region').map(day => day.getAttribute('aria-labelledby'))).toEqual([
      'agenda-2026-10-27',
      'agenda-2026-10-28',
    ]);
    expect(entriesOf('mardi 27 octobre')).toEqual([
      'workbench.calendar.all_day · holiday',
      '09:00 – 09:15 · standup',
      '12:30 – 13:30 · lunch',
    ]);
    // An all-day event ends the evening before its exclusive end day.
    expect(entriesOf('mercredi 28 octobre')).toEqual(['workbench.calendar.all_day · holiday']);
  });

  it('shows an event across midnight on each day it touches, saying it goes on', () => {
    agenda([event('night', { start: '2026-10-27T22:00:00Z', end: '2026-10-28T01:00:00Z' })]);

    expect(entriesOf('mardi 27 octobre')).toEqual(['23:00 – … · night']);
    expect(entriesOf('mercredi 28 octobre')).toEqual(['… – 02:00 · night']);
  });

  it('names an untitled event, shows where it is, and marks the open one', () => {
    agenda(
      [
        event('a', { summary: '', location: 'Salle 3' }),
        event('b', { start: '2026-10-27T10:00:00Z', end: '2026-10-27T11:00:00Z' }),
      ],
      { openId: 'primary|b' }
    );

    const [untitled, open] = within(screen.getByRole('region')).getAllByRole('link');
    expect(untitled).toHaveTextContent('workbench.calendar.no_title');
    expect(untitled).toHaveTextContent('Salle 3');
    expect(untitled).not.toHaveAttribute('aria-current');
    expect(open).toHaveAttribute('aria-current', 'true');
    expect(open).toHaveAttribute('href', '/event/b');
  });

  it('hands every link to the drill-down focus', () => {
    const { linkRef } = agenda([event('a', {})]);

    expect(linkRef).toHaveBeenCalledWith('primary|a', screen.getByRole('link'));
  });

  it('says so when the days hold nothing', () => {
    agenda([event('later', { start: '2026-11-03T08:00:00Z', end: '2026-11-03T09:00:00Z' })]);

    expect(screen.queryByRole('region')).toBeNull();
    expect(screen.getByText('workbench.calendar.empty')).toBeInTheDocument();
  });

  it('scrolls the list, not the page, to the day it opens on', () => {
    vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(function (
      this: HTMLElement
    ) {
      if (this.getAttribute('aria-labelledby') === 'agenda-2026-10-29') return 340;
      return this.tagName === 'DIV' ? 40 : 0;
    });
    const scrolled = vi.spyOn(Element.prototype, 'scrollTop', 'set');
    const page = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);

    agenda(
      [
        event('a', {}),
        event('b', { start: '2026-10-28T08:00:00Z', end: '2026-10-28T09:00:00Z' }),
        event('c', { start: '2026-10-29T08:00:00Z', end: '2026-10-29T09:00:00Z' }),
      ],
      // Not today (the 28th): the day the « +N » pointed at.
      { focusDay: '2026-10-29' }
    );

    expect(scrolled).toHaveBeenCalledWith(300);
    expect(page).not.toHaveBeenCalled();
  });
});

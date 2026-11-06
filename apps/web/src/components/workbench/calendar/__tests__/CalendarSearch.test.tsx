/**
 * Searching the calendars (ADR-369, lot 5).
 *
 * The words go to the calendars shown and the answer takes the view's place: the earliest
 * first, each one a link that opens as from the view. What could not be read is said, and
 * so is a cut. Nowhere to look is no failure: it reads as finding nothing.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { CalendarEvent, CalendarSearchAnswer } from '@/lib/workbench/types';

import { CalendarSearchBox, SearchOrView, useCalendarSearch } from '../CalendarSearch';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

function found(id: string, summary: string): CalendarEvent {
  return {
    id,
    calendar_id: 'primary',
    summary,
    all_day: false,
    start: '2026-11-05T09:00:00Z',
    end: '2026-11-05T10:00:00Z',
    location: null,
    recurring: false,
    conference_url: null,
  };
}

const ANSWER: CalendarSearchAnswer = {
  events: [found('e1', 'Budget review'), found('e2', '')],
  failed: [],
  truncated: false,
};

function Screen({ calendarIds = ['primary', 'team'] }: { calendarIds?: readonly string[] }) {
  const searching = useCalendarSearch(calendarIds);
  return (
    <>
      <CalendarSearchBox lng="en" searching={searching} />
      <SearchOrView
        lng="en"
        zone="Europe/Paris"
        searching={searching}
        hrefOf={event => `/open/${event.id}`}
        linkRef={() => undefined}
      >
        <p>the view</p>
      </SearchOrView>
    </>
  );
}

function search(words: string): void {
  const box = screen.getByRole('searchbox');
  fireEvent.change(box, { target: { value: words } });
  fireEvent.submit(box);
}

describe('searching the calendars', () => {
  beforeEach(() => {
    api.get.mockReset();
    api.get.mockResolvedValue(ANSWER);
  });

  it('shows the view while nothing is asked, and reads nothing', () => {
    renderWithProviders(<Screen />);

    expect(screen.getByText('the view')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('asks the words of the calendars shown, the blanks around them left out', async () => {
    renderWithProviders(<Screen />);

    search('  budget  ');

    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    const [path, options] = api.get.mock.calls[0];
    expect(path).toBe('/workbench/calendar/search');
    expect(options.params).toMatchObject({ q: 'budget', calendar_ids: ['primary', 'team'] });
  });

  it('takes the view’s place, each event a link that opens it', async () => {
    renderWithProviders(<Screen />);

    search('budget');

    const link = await screen.findByRole('link', { name: /Budget review/ });
    expect(link).toHaveAttribute('href', '/open/e1');
    expect(screen.queryByText('the view')).not.toBeInTheDocument();
  });

  it('names an event that has no title', async () => {
    renderWithProviders(<Screen />);

    search('budget');

    expect(await screen.findByRole('link', { name: /no_title/ })).toHaveAttribute(
      'href',
      '/open/e2'
    );
  });

  it('gives the view back once the search is cleared', async () => {
    renderWithProviders(<Screen />);
    search('budget');
    await screen.findByRole('link', { name: /Budget review/ });

    fireEvent.click(screen.getByRole('button', { name: /clear/i }));

    expect(await screen.findByText('the view')).toBeInTheDocument();
    expect(screen.getByRole('searchbox')).toHaveValue('');
  });

  it('says it found nothing, and offers no retry for it', async () => {
    api.get.mockResolvedValue({ events: [], failed: [], truncated: false });
    renderWithProviders(<Screen />);

    search('budget');

    expect(await screen.findByText('workbench.calendar.search_none')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry|try again/i })).not.toBeInTheDocument();
  });

  it('says a calendar could not be read, beside what the others gave', async () => {
    api.get.mockResolvedValue({ ...ANSWER, failed: ['team'] });
    renderWithProviders(<Screen />);

    search('budget');

    await screen.findByRole('link', { name: /Budget review/ });
    expect(screen.getByRole('status')).toHaveTextContent('workbench.calendar.search_part_failed');
  });

  it('states a cut', async () => {
    api.get.mockResolvedValue({ ...ANSWER, truncated: true });
    renderWithProviders(<Screen />);

    search('budget');

    await screen.findByRole('link', { name: /Budget review/ });
    expect(screen.getByRole('status')).toHaveTextContent('workbench.calendar.search_truncated');
  });

  it('says a failure, and retries it', async () => {
    api.get.mockRejectedValueOnce(new Error('down'));
    renderWithProviders(<Screen />);

    search('budget');

    fireEvent.click(await screen.findByRole('button', { name: /retry|try again/i }));

    expect(await screen.findByRole('link', { name: /Budget review/ })).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('reads no failure into a search with no calendar shown', async () => {
    renderWithProviders(<Screen calendarIds={[]} />);

    search('budget');

    expect(await screen.findByText('workbench.calendar.search_none')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry|try again/i })).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});

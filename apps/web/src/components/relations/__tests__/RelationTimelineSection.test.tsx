/**
 * The relationship timeline section (owner request 2026-10-24): folded, it reads
 * nothing; opened, it asks for the first page; « Older » follows the cursor.
 * The count on the toggle is every row it holds: the card's own exact totals
 * plus the mail and meetings it places.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { RelationContext, RelationDetail } from '@/hooks/useRelations';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));

import { RelationTimelineSection } from '../RelationTimelineSection';

const detail: RelationDetail = {
  display_name: 'Ana Example',
  identity_confidence: 'exact',
  open_loops: [],
  open_loops_total: 2,
  recent_calls: [],
  recent_calls_total: 1,
  memories: [],
  memories_total: 3,
  peer_messages: [],
  peer_messages_total: 0,
  sms: [],
  sms_total: 1,
  sms_available: true,
  peer_link: null,
  is_favorite: false,
  is_peer: false,
};

const call = (id: string, at: string) => ({
  kind: 'call',
  at,
  call: { id, objective: `call ${id}`, outcome: null, summary: null, created_at: at },
});

/** A provider context whose sections read fine and hold nothing: only its windows matter. */
function windowsOnly(windowDays: number, emailWindowDays: number): RelationContext {
  const section = (): RelationContext['events'] => ({
    status: 'ok',
    from_cache: false,
    generated_at: '2026-10-24T09:00:00Z',
    contact: null,
    emails: [],
    events: [],
  });
  return {
    contact: section(),
    emails: section(),
    events: section(),
    addresses_used: 0,
    window_days: windowDays,
    email_window_days: emailWindowDays,
  };
}

beforeEach(() => api.get.mockReset());

describe('RelationTimelineSection', () => {
  it('reads nothing while folded, the first page on opening, the next on « Older »', async () => {
    api.get
      .mockResolvedValueOnce({
        items: [call('c2', '2026-10-20T09:00:00Z')],
        next_cursor: 'CURSOR',
        page_size: 1,
      })
      .mockResolvedValueOnce({
        items: [call('c1', '2026-10-10T09:00:00Z')],
        next_cursor: null,
        page_size: 1,
      });
    render(<RelationTimelineSection name="Ana Example" detail={detail} context={null} lng="en" />);

    // The folded index states the card's own exact count, and asked nothing.
    const toggle = screen.getByRole('button', { name: /relations\.timeline\.title/ });
    expect(toggle).toHaveTextContent('7');
    expect(api.get).not.toHaveBeenCalled();

    fireEvent.click(toggle);
    expect(await screen.findByText('call c2')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/relations/Ana%20Example/timeline');

    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.older/ }));
    expect(await screen.findByText('call c1')).toBeInTheDocument();
    expect(api.get).toHaveBeenLastCalledWith('/relations/Ana%20Example/timeline?cursor=CURSOR');
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /relations\.timeline\.older/ })).toBeNull()
    );
    // Folding again keeps what was read: no new request on reopening.
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('counts the mail and meetings it places, and the meetings to come lead', async () => {
    const section = (overrides: Partial<RelationContext['events']>): RelationContext['events'] => ({
      status: 'ok',
      from_cache: false,
      generated_at: '2026-10-24T09:00:00Z',
      contact: null,
      emails: [],
      events: [],
      ...overrides,
    });
    const context: RelationContext = {
      contact: section({}),
      emails: section({
        emails: [
          {
            id: 'mail',
            direction: 'received',
            subject: 'The quote',
            occurred_at: '2026-10-21T09:00:00Z',
            excerpt: null,
          },
        ],
      }),
      events: section({
        events: [
          {
            id: 'next',
            summary: 'Site visit',
            starts_at: '2026-11-05T09:00:00Z',
            ends_at: null,
            is_past: false,
            role: 'attendee',
            organizer_known: true,
          },
        ],
      }),
      addresses_used: 1,
      window_days: 90,
      email_window_days: 365,
    };
    api.get.mockResolvedValueOnce({
      items: [call('c2', '2026-10-20T09:00:00Z')],
      next_cursor: null,
      page_size: 5,
    });
    render(
      <RelationTimelineSection name="Ana Example" detail={detail} context={context} lng="en" />
    );

    // 7 records of the card, one e-mail, one meeting to come.
    const toggle = screen.getByRole('button', { name: /relations\.timeline\.title/ });
    expect(toggle).toHaveTextContent('9');
    fireEvent.click(toggle);
    expect(await screen.findByText('call c2')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem').map(row => row.textContent);
    expect(rows[0]).toContain('Site visit');
    expect(rows.slice(1).map(text => (text?.includes('The quote') ? 'mail' : 'call'))).toEqual([
      'mail',
      'call',
    ]);
  });

  it('reads its first page again whenever the card re-reads its records', async () => {
    // A commitment closed from the card: the card re-reads, and a timeline
    // that kept its rows would list a closed commitment under a smaller count.
    api.get
      .mockResolvedValueOnce({
        items: [call('c2', '2026-10-20T09:00:00Z')],
        next_cursor: null,
        page_size: 5,
      })
      .mockResolvedValueOnce({ items: [], next_cursor: null, page_size: 5 });
    const { rerender } = render(
      <RelationTimelineSection name="Ana Example" detail={detail} context={null} lng="en" />
    );
    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.title/ }));
    expect(await screen.findByText('call c2')).toBeInTheDocument();

    rerender(
      <RelationTimelineSection
        name="Ana Example"
        detail={{ ...detail, recent_calls_total: 0 }}
        context={null}
        lng="en"
      />
    );
    await waitFor(() => expect(screen.queryByText('call c2')).toBeNull());
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.get).toHaveBeenLastCalledWith('/relations/Ana%20Example/timeline');
  });

  it('words a row with no text as its section does, and a call summary rides under it', async () => {
    api.get.mockResolvedValueOnce({
      items: [
        {
          kind: 'peer_message',
          at: '2026-10-22T09:00:00Z',
          peer_message: {
            id: 'p1',
            direction: 'sent',
            content: null,
            occurred_at: '2026-10-22T09:00:00Z',
          },
        },
        {
          kind: 'call',
          at: '2026-10-20T09:00:00Z',
          call: {
            id: 'c3',
            objective: 'call c3',
            outcome: null,
            summary: 'Agreed on Friday',
            created_at: '2026-10-20T09:00:00Z',
          },
        },
      ],
      next_cursor: null,
      page_size: 5,
    });
    render(<RelationTimelineSection name="Ana Example" detail={detail} context={null} lng="en" />);
    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.title/ }));

    expect(await screen.findByText('relations.peer_message_no_content')).toBeInTheDocument();
    expect(screen.getByText('call c3')).toBeInTheDocument();
    expect(screen.getByText('Agreed on Friday')).toBeInTheDocument();
  });

  it('states only the windows that apply, and none when none does', async () => {
    api.get.mockResolvedValueOnce({
      items: [call('c2', '2026-10-20T09:00:00Z')],
      next_cursor: null,
      page_size: 5,
    });
    const { rerender } = render(
      <RelationTimelineSection
        name="Ana Example"
        detail={detail}
        context={windowsOnly(0, 30)}
        lng="en"
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.title/ }));
    expect(await screen.findByText('call c2')).toBeInTheDocument();
    expect(screen.getByText('relations.emails_window')).toBeInTheDocument();
    expect(screen.queryByText(/relations\.events_window/)).toBeNull();

    rerender(
      <RelationTimelineSection
        name="Ana Example"
        detail={detail}
        context={windowsOnly(0, 0)}
        lng="en"
      />
    );
    expect(screen.getByText('call c2')).toBeInTheDocument();
    expect(screen.queryByText(/relations\.emails_window/)).toBeNull();
  });

  it('says so when the older page cannot be read, and keeps what it shows', async () => {
    api.get
      .mockResolvedValueOnce({
        items: [call('c2', '2026-10-20T09:00:00Z')],
        next_cursor: 'CURSOR',
        page_size: 1,
      })
      .mockRejectedValueOnce(new Error('offline'));
    render(<RelationTimelineSection name="Ana Example" detail={detail} context={null} lng="en" />);
    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.title/ }));
    expect(await screen.findByText('call c2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.older/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('relations.timeline.more_error');
    expect(screen.getByText('call c2')).toBeInTheDocument();
  });

  it('says so when the timeline cannot be read', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'));
    render(<RelationTimelineSection name="Ana Example" detail={detail} context={null} lng="en" />);
    fireEvent.click(screen.getByRole('button', { name: /relations\.timeline\.title/ }));
    expect(await screen.findByText('relations.timeline.error')).toBeInTheDocument();
  });
});

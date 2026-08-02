/**
 * The provider-backed sections — what the connected accounts add, what they
 * are honest about when they add nothing, and what the reader can act on.
 *
 * Exported one by one because the reader asked for a precise ORDER that
 * interleaves them with the database-local sections; each is tested on its own
 * terms. The oracles that matter most are the NEGATIVE ones: a missing
 * connector, a card with no address and an empty result produce three
 * different sentences, and only one may appear at a time.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type {
  ContactCard,
  ContextSection,
  ContextStatus,
  RelationContext,
} from '@/hooks/useRelations';

import {
  ProviderContactSection,
  ProviderEmailsSection,
  ProviderEventsSection,
  ProviderNote,
  providerNoteKey,
  selectedSubjects,
} from '../RelationProviderSections';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

// Chat deep links are REAL navigations since 2026-08-01 (ADR-192): the App
// Router restored the search params of the entry it already held, so a second
// deep link in a session left with the FIRST one's URL. The oracle is the same
// href — only the door changed.
const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
}));

function section(over: Partial<ContextSection> = {}): ContextSection {
  return {
    status: 'empty',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    contact: null,
    emails: [],
    events: [],
    ...over,
  };
}

function context(over: Partial<RelationContext> = {}): RelationContext {
  return {
    contact: section(),
    emails: section(),
    events: section(),
    addresses_used: 0,
    window_days: 90,
    email_window_days: 365,
    ...over,
  };
}

function card(over: Partial<ContactCard> = {}): ContactCard {
  return {
    display_name: 'Gérard Dupont',
    nickname: null,
    organization: 'ACME',
    occupation: null,
    birthday: null,
    biography: null,
    emails: [{ value: 'gerard@example.com', label: 'home' }],
    phones: [{ value: '+33600000000', label: 'mobile' }],
    addresses: [],
    relations: [],
    links: [],
    important_dates: [],
    messaging: [],
    ...over,
  };
}

const CARD = card();

function event(over: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    summary: 'Réunion',
    starts_at: '2026-08-02T09:00:00Z',
    ends_at: '2026-08-02T10:30:00Z',
    is_past: false,
    role: 'attendee' as const,
    organizer_known: true,
    ...over,
  };
}

describe('ProviderContactSection', () => {
  it('renders the organization, the addresses and the phones with their labels', async () => {
    const { user } = renderWithProviders(
      <ProviderContactSection
        section={section({ status: 'ok', contact: CARD })}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /relations.section_contact/ }));
    expect(screen.getByText('ACME')).toBeInTheDocument();
    expect(screen.getByText('gerard@example.com')).toBeInTheDocument();
    // The global stub echoes keys: the label goes through i18n like any other
    // user-visible word. Its fallback for an UNKNOWN provider label is proven
    // in `ContactCardBody.test.tsx`, where the stub honours `defaultValue`.
    expect(screen.getByText('relations.contact_label.home')).toBeInTheDocument();
    expect(screen.getByText('+33600000000')).toBeInTheDocument();
  });

  it('renders nothing when the section carries no card', () => {
    const { container } = renderWithProviders(
      <ProviderContactSection section={section()} busy={false} onRefresh={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('starts CLOSED and opens on demand, announcing both states', async () => {
    // The reader lands on a compact index of the relationship and opens what
    // they came for, instead of scrolling past seven sections to reach the
    // eighth.
    const { user } = renderWithProviders(
      <ProviderContactSection
        section={section({ status: 'ok', contact: CARD })}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    const toggle = screen.getByRole('button', { name: /relations.section_contact/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('ACME')).not.toBeVisible();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('ACME')).toBeVisible();
  });

  it('offers a refresh, because this section is cached for hours', async () => {
    const onRefresh = vi.fn();
    const { user } = renderWithProviders(
      <ProviderContactSection
        section={section({ status: 'ok', contact: CARD })}
        busy={false}
        onRefresh={onRefresh}
      />
    );
    await user.click(screen.getByRole('button', { name: 'relations.refresh_section' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});

describe('ProviderEmailsSection', () => {
  const emails = section({
    status: 'ok',
    emails: [
      {
        id: 'm1',
        direction: 'received',
        subject: 'Devis chantier',
        occurred_at: '2026-07-29T09:00:00Z',
        excerpt: 'Bonjour, voici le devis pour le chantier de la rue Victor Hugo.',
      },
      {
        id: 'm2',
        direction: 'sent',
        subject: 'Relance',
        occurred_at: '2026-07-28T09:00:00Z',
        excerpt: null,
      },
    ],
  });

  /** Renders the section and OPENS it — the panel starts folded. */
  async function renderEmails() {
    const utils = renderWithProviders(
      <ProviderEmailsSection
        section={emails}
        personName="Gérard Dupont"
        windowDays={365}
        lng="fr"
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    await utils.user.click(screen.getByRole('button', { name: /relations.section_emails/ }));
    return utils;
  }

  it('renders both directions as translated text', async () => {
    await renderEmails();
    expect(screen.getByText('Devis chantier')).toBeInTheDocument();
    expect(screen.getByText('relations.peer_message_received')).toBeInTheDocument();
    expect(screen.getByText('relations.peer_message_sent')).toBeInTheDocument();
  });

  it('states the window it searched instead of a total it cannot prove', async () => {
    await renderEmails();
    expect(screen.getByText('relations.emails_window')).toBeInTheDocument();
  });

  it('shows the excerpt under the subject — "Re: Re: point" says nothing', async () => {
    await renderEmails();
    expect(
      screen.getByText('Bonjour, voici le devis pour le chantier de la rue Victor Hugo.')
    ).toBeInTheDocument();
  });

  it('renders NOTHING when the provider returned no preview', async () => {
    const { container } = await renderEmails();
    // 'Relance' has excerpt: null — its row must carry the subject and no
    // empty line pretending the message was blank.
    const relance = screen.getByText('Relance').closest('label');
    expect(relance).not.toBeNull();
    expect(relance?.querySelectorAll('.line-clamp-2')).toHaveLength(0);
    expect(container.querySelectorAll('.line-clamp-2')).toHaveLength(1);
  });

  it('dates each message absolutely, next to the relative label', async () => {
    await renderEmails();
    expect(screen.getByText('relations.peer_message_received')).toBeVisible();
    // Two representations of the same instant: how long ago, and when.
    expect(screen.getAllByText(/\d{2}:\d{2}/).length).toBeGreaterThan(0);
  });

  it('offers the summary only once something is selected', async () => {
    const { user } = await renderEmails();
    expect(screen.queryByRole('button', { name: /relations.emails_summarize/ })).toBeNull();

    await user.click(screen.getAllByRole('checkbox')[0]);
    expect(screen.getByRole('button', { name: /relations.emails_summarize/ })).toBeInTheDocument();
  });

  it('sends the request to the chat as an auto-sent INTENT', async () => {
    openChat.mockClear();
    const { user } = await renderEmails();

    await user.click(screen.getAllByRole('checkbox')[1]);
    await user.click(screen.getByRole('button', { name: /relations.emails_summarize/ }));

    expect(openChat).toHaveBeenCalledTimes(1);
    const href = String(openChat.mock.calls[0][0]);
    // `?intent=` and not `?draft=`: ticking messages and pressing a named
    // button IS the deliberate act — and the request goes to LIA, not to a
    // human (ADR-173, where `?draft=` is reserved for writing to someone).
    expect(href).toContain('intent=');
    expect(href).not.toContain('draft=');
  });

  it('counts only the ticked messages STILL on the page', async () => {
    // A refresh can retire a message whose id is still selected. Offering to
    // summarize three while handing over two would be a claim the request
    // itself contradicts.
    const { user, rerender } = renderWithProviders(
      <ProviderEmailsSection
        section={emails}
        personName="Gérard Dupont"
        windowDays={365}
        lng="fr"
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /relations.section_emails/ }));
    await user.click(screen.getAllByRole('checkbox')[0]);
    await user.click(screen.getAllByRole('checkbox')[1]);
    expect(screen.getByRole('button', { name: /relations.emails_summarize/ })).toBeVisible();

    // The section comes back with only ONE of the two selected messages.
    rerender(
      <ProviderEmailsSection
        section={section({ status: 'ok', emails: [emails.emails[0]] })}
        personName="Gérard Dupont"
        windowDays={365}
        lng="fr"
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /relations.section_emails/ }));
    expect(selectedSubjects([emails.emails[0]], [emails.emails[0].id, 'gone'])).toBe(
      '« Devis chantier »'
    );
  });

  it('unticking removes the message from the request', async () => {
    const { user } = await renderEmails();
    const [first] = screen.getAllByRole('checkbox');
    await user.click(first);
    await user.click(first);
    expect(screen.queryByRole('button', { name: /relations.emails_summarize/ })).toBeNull();
  });
});

describe('ProviderEventsSection', () => {
  it('tells the two roles apart, in words', () => {
    renderWithProviders(
      <ProviderEventsSection
        section={section({
          status: 'ok',
          events: [
            event({ id: 'org', role: 'organizer' }),
            event({ id: 'att', role: 'attendee', summary: 'Chantier' }),
          ],
        })}
        windowDays={90}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByText('relations.event_role_organizer')).toBeInTheDocument();
    expect(screen.getByText('relations.event_role_attendee')).toBeInTheDocument();
  });

  it('claims no role at all when the provider exposes no organizer', () => {
    // Apple's events carry none. Labelling everything "attendee" would state a
    // role nobody verified (ADR-184).
    renderWithProviders(
      <ProviderEventsSection
        section={section({
          status: 'ok',
          events: [event({ organizer_known: false })],
        })}
        windowDays={90}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByText('Réunion')).toBeInTheDocument();
    expect(screen.queryByText('relations.event_role_attendee')).toBeNull();
    expect(screen.queryByText('relations.event_role_organizer')).toBeNull();
  });

  it('shows the SLOT — the day and both hours, not only the distance', async () => {
    // "dans 5 j" says how far off; it never says whether the reader can be
    // there. A meeting is a span, so both edges are printed.
    const { user } = renderWithProviders(
      <ProviderEventsSection
        section={section({ status: 'ok', events: [event()] })}
        windowDays={90}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /relations.section_events/ }));
    // Testing Library normalizes whitespace, so the matcher stays flexible…
    const slot = screen.getByText(/\d{2}:\d{2}\s*–\s*\d{2}:\d{2}/);
    expect(slot).toBeVisible();
    // …and the RAW text pins the narrow no-break spaces: on a 320 px screen a
    // plain space would let the range wrap onto two lines mid-slot.
    expect(slot.textContent).toMatch(/ – /);
  });

  it('prints a single instant when the calendar gave no end', async () => {
    const { user } = renderWithProviders(
      <ProviderEventsSection
        section={section({ status: 'ok', events: [event({ ends_at: null })] })}
        windowDays={90}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /relations.section_events/ }));
    // No end means no range — never a dash with nothing after it.
    expect(screen.queryByText(/\d{2}:\d{2}\s*–/)).toBeNull();
    expect(screen.getByText(/\d{2}:\d{2}/)).toBeVisible();
  });

  it('flags what is still ahead', () => {
    renderWithProviders(
      <ProviderEventsSection
        section={section({ status: 'ok', events: [event(), event({ id: 'p', is_past: true })] })}
        windowDays={90}
        busy={false}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getAllByText('relations.event_upcoming')).toHaveLength(1);
  });
});

describe('the one sentence unusable sections may say', () => {
  const all = (status: ContextStatus) =>
    context({
      contact: section({ status }),
      emails: section({ status }),
      events: section({ status }),
    });

  it('names the ADDRESS BOOK when that is what is missing', () => {
    // Contacts absent but mail connected: saying "no address on this contact
    // card" would describe a card that does not exist.
    expect(
      providerNoteKey(
        context({
          contact: section({ status: 'not_configured' }),
          emails: section({ status: 'no_address' }),
          events: section({ status: 'no_address' }),
        })
      )
    ).toBe('relations.provider_none');
  });

  it('invites connecting an account when NOTHING is plugged in', () => {
    expect(providerNoteKey(all('not_configured'))).toBe('relations.provider_none');
  });

  it('explains a card with no address rather than claiming an empty mailbox', () => {
    expect(
      providerNoteKey(
        context({
          contact: section({ status: 'ok', contact: { ...CARD, emails: [] } }),
          emails: section({ status: 'no_address' }),
          events: section({ status: 'no_address' }),
        })
      )
    ).toBe('relations.provider_no_address');
  });

  it('reports a read failure without pretending the exchange is empty', () => {
    expect(providerNoteKey(context({ emails: section({ status: 'error' }) }))).toBe(
      'relations.provider_error'
    );
  });

  it('stays silent when one section merely found nothing', () => {
    expect(
      providerNoteKey(
        context({
          contact: section({ status: 'ok', contact: CARD }),
          emails: section({ status: 'empty' }),
          events: section({ status: 'empty' }),
        })
      )
    ).toBeNull();
  });

  it('stays silent when only mail is unconnected — that is a choice, not a gap', () => {
    expect(
      providerNoteKey(
        context({
          contact: section({ status: 'ok', contact: CARD }),
          emails: section({ status: 'not_configured' }),
          events: section({ status: 'empty' }),
        })
      )
    ).toBeNull();
  });

  it('renders nothing at all for a null key', () => {
    const { container } = renderWithProviders(<ProviderNote noteKey={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('selectedSubjects', () => {
  const emails = [
    { id: 'm1', direction: 'received' as const, subject: 'Devis', occurred_at: null, excerpt: null },
    {
      id: 'm2',
      direction: 'sent' as const,
      subject: 'Relance',
      occurred_at: null,
      excerpt: null,
    },
    { id: 'm3', direction: 'received' as const, subject: 'Merci', occurred_at: null, excerpt: null },
  ];

  it('carries ONLY what was ticked', () => {
    expect(selectedSubjects(emails, ['m2'])).toBe('« Relance »');
  });

  it('keeps the list order, not the click order', () => {
    // The reader asked about a conversation; a chronological request reads
    // like one.
    expect(selectedSubjects(emails, ['m3', 'm1'])).toBe('« Devis », « Merci »');
  });

  it('is empty when nothing is ticked', () => {
    expect(selectedSubjects(emails, [])).toBe('');
  });

  it('ignores an id that is no longer on the page', () => {
    // A refresh can retire a message while its id is still selected.
    expect(selectedSubjects(emails, ['gone', 'm1'])).toBe('« Devis »');
  });
});

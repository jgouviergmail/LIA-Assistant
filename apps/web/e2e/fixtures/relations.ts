import type { MockRoute } from './api-mock';

/**
 * The card's own records on one line (owner request 2026-10-24), exactly as
 * the API pages them: newest first, four to a page, so the fifth (the memory)
 * waits behind a cursor and a scan sees the « Older » control as well as the
 * rows — the relayed message whose text expired included.
 */
export const relationTimelinePage = {
  items: [
    {
      kind: 'peer_message',
      at: '2026-07-27T18:00:00Z',
      open_loop: null,
      call: null,
      memory: null,
      peer_message: {
        id: 'pm1',
        direction: 'received',
        content: 'Gérard vous fait dire qu’il sera en retard.',
        occurred_at: '2026-07-27T18:00:00Z',
      },
      sms: null,
    },
    {
      kind: 'peer_message',
      at: '2026-07-26T08:00:00Z',
      open_loop: null,
      call: null,
      memory: null,
      peer_message: {
        id: 'pm2',
        direction: 'sent',
        content: null,
        occurred_at: '2026-07-26T08:00:00Z',
      },
      sms: null,
    },
    {
      kind: 'call',
      at: '2026-07-25T10:00:00Z',
      open_loop: null,
      call: {
        id: 'c1',
        objective: 'Anniversaire surprise',
        outcome: 'objective_met',
        summary: 'Il est partant.',
        created_at: '2026-07-25T10:00:00Z',
      },
      memory: null,
      peer_message: null,
      sms: null,
    },
    {
      kind: 'open_loop',
      at: '2026-07-21T09:00:00Z',
      open_loop: {
        id: 'l1',
        subject: 'Rendre la perceuse',
        direction: 'user_owes',
        due_hint: null,
        days_open: 4,
        opened_at: '2026-07-21T09:00:00Z',
      },
      call: null,
      memory: null,
      peer_message: null,
      sms: null,
    },
  ],
  next_cursor: 'e2e-after-the-open-loop',
  page_size: 4,
};

/**
 * What `/relations/{name}/context` answers for Gérard: the address-book entry,
 * the mail and the meetings. Exported so a spec can derive a variant (another
 * value on the card) without restating the whole payload.
 */
export const relationContextPayload = {
  contact: {
    status: 'ok',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    contact: {
      display_name: 'Gérard Dupont',
      nickname: null,
      organization: 'Menuiserie Dupont',
      occupation: 'Menuisier',
      birthday: '--04-07',
      biography: null,
      emails: [{ value: 'gerard@example.com', label: 'work' }],
      phones: [{ value: '+33600000000', label: 'mobile' }],
      addresses: [
        {
          // Deliberately long, with spaces: it must wrap on the spaces at
          // 320 px, never be chopped mid-word.
          value: '12 rue des Lilas Blancs, 69008 Lyon Métropole, France',
          label: 'home',
        },
      ],
      relations: [{ value: 'Claire Lefèvre', label: 'spouse' }],
      // One unbreakable token far wider than 320 px: the case that decides
      // whether the card overflows the viewport or wraps inside it.
      links: [
        {
          value: 'https://example.com/menuiserie-dupont/realisations/terrasses-bois',
          label: null,
        },
      ],
      important_dates: [{ value: '2011-09-03', label: 'anniversary' }],
      messaging: [],
    },
    emails: [],
    events: [],
  },
  emails: {
    status: 'ok',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    contact: null,
    emails: [
      {
        id: 'm1',
        direction: 'received',
        subject: 'Devis pour la terrasse',
        occurred_at: '2026-07-28T09:00:00Z',
        // The whole mail contract (`ExchangedEmail`): an excerpt is the
        // second line of its row, in its section and on the timeline.
        excerpt: 'Bonjour, voici le chiffrage révisé, à valider avant vendredi.',
      },
    ],
    events: [],
  },
  events: {
    status: 'ok',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    contact: null,
    emails: [],
    events: [
      {
        id: 'e1',
        summary: 'Visite du chantier',
        starts_at: '2026-08-05T09:00:00Z',
        // The whole event contract (`SharedEvent`): the API always sends it.
        ends_at: null,
        is_past: false,
        role: 'organizer',
        organizer_known: true,
      },
    ],
  },
  addresses_used: 1,
  window_days: 90,
  email_window_days: 365,
};

/**
 * The 360° relationship fixture, shared by every spec that opens a contact.
 *
 * Extracted 2026-08-03: the accessibility journey and the mobile-overflow
 * guard each carried their own copy of these ~180 lines. Two copies of one
 * payload do not stay equal — the day a section gains a field, one spec
 * exercises it and the other silently stops covering the case it was written
 * for, with both still green.
 *
 * Deliberately rich: every section is populated INCLUDING the relayed peer
 * messages and the "no text kept" degraded case, so a scan sees the coloured
 * pills, the section cards and the reply control rather than empty shells.
 */
export const relationsData: MockRoute[] = [
  {
    url: '**/api/v1/relations',
    json: {
      relations: [
        {
          display_name: 'Gérard Dupont',
          identity_confidence: 'exact',
          open_loops_count: 2,
          calls_count: 1,
          peer_messages_count: 2,
          last_interaction_at: '2026-07-28T09:00:00Z',
          is_favorite: true,
          is_peer: true,
        },
        {
          // A starred relationship with NO live signal: exercises the "no
          // recent signal" italic and the empty pills row, a branch the
          // populated card above never renders.
          display_name: 'Mémé Jeanne',
          identity_confidence: 'exact',
          open_loops_count: 0,
          calls_count: 0,
          peer_messages_count: 0,
          last_interaction_at: null,
          is_favorite: false,
          is_peer: false,
        },
        // Enough people to bring the TOOLBAR out (search + sort select +
        // filter chips appear past the threshold) — otherwise the scan would
        // silently skip every control it introduced. One of them is dormant,
        // so the "dormant" chip is scanned too.
        ...Array.from({ length: 9 }, (_, index) => ({
          display_name: `Contact ${index}`,
          identity_confidence: 'exact',
          open_loops_count: index % 3,
          calls_count: index % 2,
          peer_messages_count: 0,
          last_interaction_at: index === 0 ? '2025-01-05T09:00:00Z' : '2026-07-20T09:00:00Z',
          is_favorite: false,
          is_peer: index === 1,
        })),
      ],
      // Stated rather than left to the hook's fallback: a fixture that relies
      // on a client-side default stops testing the contract it stands for.
      debrief_enabled: true,
    },
  },
  {
    // FIRST among the `/relations/...` routes, not last: Playwright resolves
    // route handlers LAST-REGISTERED-FIRST (see `fixtures/api-mock.ts`).
    // Declared last, this catch-all won and answered `/relations/overview-scope`
    // with a RelationDetail; the panel then read `scope.sections.length` off an
    // object that has no `sections` and died behind its error boundary.
    url: '**/api/v1/relations/*',
    json: {
      display_name: 'Gérard Dupont',
      identity_confidence: 'normalized',
      open_loops: [
        {
          id: 'l1',
          subject: 'Rendre la perceuse',
          direction: 'user_owes',
          due_hint: null,
          days_open: 4,
          opened_at: '2026-07-21T09:00:00Z',
        },
      ],
      recent_calls: [
        {
          id: 'c1',
          objective: 'Anniversaire surprise',
          outcome: 'objective_met',
          summary: 'Il est partant.',
          created_at: '2026-07-25T10:00:00Z',
        },
      ],
      memories: [
        { id: 'm1', content: 'Aime la randonnée en montagne.', created_at: '2026-07-18T08:30:00Z' },
      ],
      open_loops_total: 1,
      recent_calls_total: 1,
      memories_total: 1,
      peer_messages_total: 2,
      peer_messages: [
        {
          id: 'pm1',
          direction: 'received',
          content: 'Gérard vous fait dire qu’il sera en retard.',
          occurred_at: '2026-07-27T18:00:00Z',
        },
        { id: 'pm2', direction: 'sent', content: null, occurred_at: '2026-07-26T08:00:00Z' },
      ],
      peer_link: {
        connected_since: '2026-06-01T10:00:00Z',
        shared_by_me: [{ domain: 'calendar', level: 'availability' }],
        shared_with_me: [{ domain: 'task', level: 'titles' }],
      },
      is_favorite: true,
      is_peer: true,
    },
  },
  {
    // AFTER the catch-all above, so this more specific route wins (LIFO).
    url: '**/api/v1/relations/overview-scope',
    json: {
      sections: ['contact', 'open_loops', 'calls', 'memories', 'peer_messages', 'emails', 'events'],
      directions: ['received', 'sent'],
      roles: ['attendee', 'organizer'],
      max_items: 5,
    },
  },
  {
    // AFTER the catch-all above (LIFO). The single-segment glob does not match
    // a two-segment path anyway, but the order now states the intent correctly.
    url: '**/api/v1/relations/*/context',
    json: relationContextPayload,
  },
  {
    // AFTER the catch-all (LIFO), like `/context` above. Serving a READY
    // debrief is what puts the section's real geometry in front of axe: an
    // unserved route leaves the panel in its "not built yet" state, which is
    // three words and a glyph — a scan that would pass over a component nobody
    // rendered.
    url: '**/api/v1/relations/*/debrief',
    json: {
      status: 'ready',
      person: 'Gérard Dupont',
      body: {
        headline: 'Vous lui devez une réponse sur le devis.',
        where_we_stand:
          'Deux échanges cette semaine, tous deux à votre initiative. Le chantier avance.',
        open_points: ['Répondre au devis du 28 juillet', 'Confirmer la date de visite'],
        suggested_next_step: 'Lui renvoyer le devis signé avant vendredi.',
        notable_facts: ['Menuisier, Menuiserie Dupont', 'Anniversaire le 7 avril'],
      },
      generated_at: '2026-07-30T06:30:00Z',
      generated_for: '2026-07-30',
      sections_used: ['contact', 'open_commitments', 'recent_calls'],
      unavailable: ['events'],
      can_rebuild: true,
    },
  },
  {
    // AFTER the catch-all (LIFO), like `/context`.
    url: '**/api/v1/relations/*/timeline',
    json: relationTimelinePage,
  },
  {
    // The address-book actions read the account's connectors: a call is
    // offered only on a number and an ACTIVE telephony connector (owner
    // request 2026-10-21). None here, so the card offers no call.
    url: /\/api\/v1\/connectors\?fresh=true$/,
    json: { connectors: [] },
  },
];

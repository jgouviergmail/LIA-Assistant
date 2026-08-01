/**
 * RelationDetailPanel (N-09) — the 360° view of one relationship.
 *
 * What must hold: sections render their items; the best-effort banner shows
 * only on a normalized match; the "prepare 360°" button deep-links a chat
 * ?intent= (ADR-173); back returns to the list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { RelationDetail, RelationPeerLink, RelationPeerMessage } from '@/hooks/useRelations';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const { useRelationDetail, useRelationContext, useOverviewScope, saveScope } = vi.hoisted(() => ({
  useRelationDetail: vi.fn(),
  useRelationContext: vi.fn(),
  useOverviewScope: vi.fn(),
  saveScope: vi.fn(),
}));
// PARTIAL mock: the module also exports the section/direction/role vocabulary
// the scope selector is built from. Replacing it wholesale silently empties
// those lists, and the panel then renders a selector with no boxes at all.
vi.mock('@/hooks/useRelations', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useRelations')>()),
  useRelationDetail,
  useRelationContext,
  useOverviewScope,
}));

import { RelationDetailPanel } from '../RelationDetailPanel';

function detail(over: Partial<RelationDetail> = {}): RelationDetail {
  return {
    display_name: 'Gérard Dupont',
    identity_confidence: 'exact',
    open_loops: [
      {
        id: 'l1',
        subject: 'Rendre la perceuse',
        direction: 'user_owes',
        due_hint: null,
        days_open: 4,
      },
    ],
    recent_calls: [
      {
        id: 'c1',
        objective: 'Anniversaire',
        outcome: 'objective_met',
        summary: 'RAS',
        created_at: '2026-07-20T10:00:00Z',
      },
    ],
    memories: [{ id: 'm1', content: 'Aime la randonnée' }],
    open_loops_total: 1,
    recent_calls_total: 1,
    memories_total: 1,
    peer_messages: [],
    peer_messages_total: 0,
    peer_link: null,
    is_favorite: false,
    is_peer: false,
    ...over,
  };
}

function peerMessage(over: Partial<RelationPeerMessage> = {}): RelationPeerMessage {
  return {
    id: 'pm1',
    direction: 'received',
    content: 'Gérard vous fait dire qu’il sera en retard.',
    occurred_at: '2026-07-29T10:00:00Z',
    ...over,
  };
}

function renderPanel(
  over: Partial<{
    name: string;
    isFavorite: boolean;
    onToggleFavorite: (name: string, nextValue: boolean) => void;
    onBack: () => void;
  }> = {}
) {
  const onToggleFavorite = vi.fn(over.onToggleFavorite);
  const onBack = vi.fn(over.onBack);
  const utils = renderWithProviders(
    <RelationDetailPanel
      name={over.name ?? 'Gérard Dupont'}
      lng="fr"
      isFavorite={over.isFavorite ?? false}
      onToggleFavorite={onToggleFavorite}
      onBack={onBack}
    />
  );
  return { ...utils, onToggleFavorite, onBack };
}

beforeEach(() => {
  // `mockReset`, not `mockClear`: one test below installs an implementation on
  // `push` to observe call ORDER, and a cleared-but-not-reset mock would keep
  // running it for every later test.
  push.mockReset();
  useRelationDetail.mockReset();
  // The provider sections are a SEPARATE query — silent by default here so
  // these tests keep asserting the database-local half on its own.
  useRelationContext.mockReturnValue({
    context: null,
    loading: false,
    refreshing: [],
    error: false,
    refreshSections: vi.fn(),
  });
  saveScope.mockReset();
  saveScope.mockResolvedValue(true);
  useOverviewScope.mockReturnValue({
    scope: {
      sections: ['contact', 'open_loops', 'calls', 'memories', 'peer_messages', 'emails', 'events'],
      directions: ['received', 'sent'],
      roles: ['attendee', 'organizer'],
      max_items: 5,
    },
    loading: false,
    saving: false,
    save: saveScope,
  });
});

/** Open the scope section and press its "run" button — the only entry point. */
async function runTheOverview(user: ReturnType<typeof renderPanel>['user']) {
  await user.click(screen.getByRole('button', { name: /relations.scope_title/ }));
  await user.click(screen.getByRole('button', { name: /relations.scope_launch/ }));
}

/** Open a folded section — every section starts closed by design. */
async function openSection(user: ReturnType<typeof renderPanel>['user'], titleKey: string) {
  await user.click(screen.getByRole('button', { name: new RegExp(titleKey) }));
}

describe('RelationDetailPanel', () => {
  it('renders each populated section once opened', async () => {
    // Sections start FOLDED: the panel is an index the reader opens, so the
    // oracle opens them too rather than reading hidden text.
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const { user } = renderPanel();

    for (const [titleKey, content] of [
      ['relations.section_open_loops', 'Rendre la perceuse'],
      ['relations.section_calls', 'Anniversaire'],
      ['relations.section_memories', 'Aime la randonnée'],
    ] as const) {
      await openSection(user, titleKey);
      expect(screen.getByText(content)).toBeVisible();
    }
  });

  it('shows every section heading with its exact count while folded', () => {
    // Folded, the badge is the only thing left to choose from — so it must be
    // on the toggle, not inside the panel.
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    renderPanel();

    const toggle = screen.getByRole('button', { name: /relations.section_open_loops/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveTextContent('1');
    expect(screen.getByText('Rendre la perceuse')).not.toBeVisible();
  });

  it('shows the best-effort banner on a normalized match', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ identity_confidence: 'normalized', memories: [] }),
      loading: false,
      error: false,
    });
    renderPanel({ name: 'Gérard' });
    expect(screen.getByText('relations.identity_best_effort')).toBeInTheDocument();
  });

  it('shows the best-effort banner whenever a memory is attached, even on an exact match', () => {
    // Memories match by name substring — they can over-match even when the
    // loop/call identity is EXACT, so the caveat must show.
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    renderPanel();
    expect(screen.getByText('relations.identity_best_effort')).toBeInTheDocument();
  });

  it('hides the banner on an exact match with no memories', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ memories: [] }),
      loading: false,
      error: false,
    });
    renderPanel();
    expect(screen.queryByText('relations.identity_best_effort')).not.toBeInTheDocument();
  });

  it('deep-links a 360° preparation as a chat intent (ADR-173)', async () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const { user } = renderPanel();
    await runTheOverview(user);
    expect((push.mock.calls[0][0] as string).startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('offers the 360° run ONLY inside the scope section', async () => {
    // A second copy in the header was a shortcut past the very choice the
    // section exists to offer — and the two could disagree on what was saved.
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const { user } = renderPanel();
    // Absent even while the scope section is FOLDED — the header carried it.
    expect(screen.queryByRole('button', { name: /relations.prepare_360/ })).toBeNull();

    await user.click(screen.getByRole('button', { name: /relations.scope_title/ }));
    expect(screen.getByRole('button', { name: /relations.scope_launch/ })).toBeVisible();
  });

  describe('the 360° scope is a guarantee, not a hint', () => {
    it('SAVES the scope before opening the chat', async () => {
      // The `?intent=` carries prose only, so the tool reads the stored scope.
      // Navigating first would race the write and hand the assistant the
      // PREVIOUS selection, with nothing on screen saying so.
      const order: string[] = [];
      saveScope.mockImplementation(async () => {
        // Yields once: a caller that fired the save WITHOUT awaiting it would
        // navigate first, and the order below would catch it.
        await Promise.resolve();
        order.push('save');
        return true;
      });
      push.mockImplementation(() => order.push('push'));
      useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
      const { user } = renderPanel();

      await runTheOverview(user);
      expect(order).toEqual(['save', 'push']);
    });

    it('applies what the reader just ticked, not what was stored', async () => {
      useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
      const { user } = renderPanel();

      await user.click(screen.getByRole('button', { name: /relations.scope_title/ }));
      await user.click(screen.getByRole('checkbox', { name: 'relations.section_calls' }));
      await user.click(screen.getByRole('button', { name: /relations.scope_launch/ }));

      expect(saveScope).toHaveBeenCalledTimes(1);
      expect(saveScope.mock.calls[0][0].sections).not.toContain('calls');
      expect(saveScope.mock.calls[0][0].sections).toContain('contact');
    });

    it('still opens the chat when the scope could not be saved', async () => {
      // A write that failed leaves the STORED scope applying — a worse answer
      // than asked for, but never a button that promised something and hung.
      saveScope.mockResolvedValue(false);
      useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
      const { user } = renderPanel();
      await runTheOverview(user);
      expect(push).toHaveBeenCalledTimes(1);
    });
  });

  it('returns to the list', async () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const { user, onBack } = renderPanel();
    await user.click(screen.getByRole('button', { name: 'relations.back' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('toggles the star from the identity header', async () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const { user, onToggleFavorite } = renderPanel({ isFavorite: true });
    const star = screen.getByRole('button', { name: 'relations.favorite_remove' });
    expect(star).toHaveAttribute('aria-pressed', 'true');
    await user.click(star);
    expect(onToggleFavorite).toHaveBeenCalledWith('Gérard Dupont', false);
  });

  it('shows the peers badge only for a connected LIA user', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ is_peer: true }),
      loading: false,
      error: false,
    });
    renderPanel();
    expect(screen.getByText('relations.peer_badge')).toBeInTheDocument();
  });

  describe('progressive disclosure', () => {
    const manyLoops = (count: number) =>
      Array.from({ length: count }, (_, index) => ({
        id: `l${index}`,
        subject: `Engagement ${index}`,
        direction: 'user_owes',
        due_hint: null,
        days_open: index,
      }));

    it('shows the EXACT total, not the number of rendered rows', async () => {
      // The silent-cap defect: a section holding 137 items rendered 10 and
      // said "10". The pill is a claim — it must state what exists.
      useRelationDetail.mockReturnValue({
        detail: detail({ open_loops: manyLoops(25), open_loops_total: 137 }),
        loading: false,
        error: false,
      });
      const { user } = renderPanel();
      await openSection(user, 'relations.section_open_loops');
      expect(screen.getByText('137')).toBeVisible();
      expect(screen.getByText('Engagement 0')).toBeVisible();
      expect(screen.queryByText('Engagement 10')).toBeNull();
    });

    it('reveals the rest of the loaded page on demand', async () => {
      useRelationDetail.mockReturnValue({
        detail: detail({ open_loops: manyLoops(25), open_loops_total: 25 }),
        loading: false,
        error: false,
      });
      const { user } = renderPanel();
      await openSection(user, 'relations.section_open_loops');

      await user.click(screen.getByRole('button', { name: /relations.show_more/ }));
      expect(screen.getByText('Engagement 24')).toBeVisible();
      expect(screen.queryByRole('button', { name: /relations.show_more/ })).toBeNull();
    });

    it('says what the page could not carry rather than hiding it', async () => {
      useRelationDetail.mockReturnValue({
        detail: detail({ open_loops: manyLoops(25), open_loops_total: 137 }),
        loading: false,
        error: false,
      });
      const { user } = renderPanel();
      await openSection(user, 'relations.section_open_loops');

      expect(screen.queryByText('relations.more_not_shown')).toBeNull();
      await user.click(screen.getByRole('button', { name: /relations.show_more/ }));
      expect(screen.getByText('relations.more_not_shown')).toBeVisible();
    });

    it('states the gap even when there is no "show more" to click', async () => {
      // A section cap of 10 or less leaves nothing to reveal, so the notice
      // must not wait for an expansion that can never happen — otherwise the
      // pill claims 137 above ten rows with nothing accounting for the gap.
      useRelationDetail.mockReturnValue({
        detail: detail({ open_loops: manyLoops(8), open_loops_total: 137 }),
        loading: false,
        error: false,
      });
      const { user } = renderPanel();
      await openSection(user, 'relations.section_open_loops');
      expect(screen.queryByRole('button', { name: /relations.show_more/ })).toBeNull();
      expect(screen.getByText('relations.more_not_shown')).toBeVisible();
    });

    it('offers no control when everything already fits', () => {
      useRelationDetail.mockReturnValue({
        detail: detail({ open_loops: manyLoops(3), open_loops_total: 3 }),
        loading: false,
        error: false,
      });
      renderPanel();
      expect(screen.queryByRole('button', { name: /relations.show_more/ })).toBeNull();
      expect(screen.queryByText('relations.more_not_shown')).toBeNull();
    });
  });

  describe('relayed messages', () => {
    it('renders the exchange with its direction as translated text', () => {
      useRelationDetail.mockReturnValue({
        detail: detail({
          peer_messages: [
            peerMessage(),
            peerMessage({ id: 'pm2', direction: 'sent', content: null }),
          ],
        }),
        loading: false,
        error: false,
      });
      renderPanel();

      // By ROLE, not by text: the scope selector above lists every source as
      // a checkbox, so the section NAME now appears twice on the page — once
      // as "include this in the 360°", once as the section itself.
      expect(
        screen.getByRole('button', { name: /relations.section_peer_messages/ })
      ).toBeInTheDocument();
      expect(screen.getByText(/sera en retard/)).toBeInTheDocument();
      // Direction is never carried by the arrow alone. Scoped to the section
      // for the same reason — the selector reuses these two labels.
      const section = screen
        .getByRole('button', {
          name: /relations.section_peer_messages/,
        })
        .closest('section') as HTMLElement;
      expect(within(section).getByText('relations.peer_message_received')).toBeInTheDocument();
      expect(within(section).getByText('relations.peer_message_sent')).toBeInTheDocument();
    });

    it('says plainly when a message has no text left', () => {
      useRelationDetail.mockReturnValue({
        detail: detail({ peer_messages: [peerMessage({ content: null })] }),
        loading: false,
        error: false,
      });
      renderPanel();
      expect(screen.getByText('relations.peer_message_no_content')).toBeInTheDocument();
    });

    it('hides the section when nothing was exchanged', () => {
      useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
      renderPanel();
      expect(screen.queryByRole('button', { name: /relations.section_peer_messages/ })).toBeNull();
    });

    it('counts messages in the empty state', () => {
      useRelationDetail.mockReturnValue({
        detail: detail({
          open_loops: [],
          recent_calls: [],
          memories: [],
          peer_messages: [peerMessage()],
        }),
        loading: false,
        error: false,
      });
      renderPanel();
      expect(screen.queryByText('relations.detail_empty')).toBeNull();
    });
  });
});

describe('RelationDetailPanel — quick actions', () => {
  beforeEach(() => {
    push.mockClear();
    useRelationDetail.mockReset();
  });

  it('always offers to call and to track a commitment', () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    renderPanel();
    expect(screen.getByRole('button', { name: 'relations.action_call' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'relations.action_loop' })).toBeInTheDocument();
  });

  it('offers to write only while the connection is live', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ is_peer: true }),
      loading: false,
      error: false,
    });
    const { unmount } = renderPanel();
    expect(screen.getByRole('button', { name: 'relations.action_message' })).toBeInTheDocument();
    unmount();

    // A removed connection leaves its past messages behind but cannot relay:
    // offering it would promise something that cannot happen.
    useRelationDetail.mockReturnValue({
      detail: detail({ is_peer: false, peer_messages: [peerMessage()], peer_messages_total: 1 }),
      loading: false,
      error: false,
    });
    renderPanel();
    expect(screen.queryByRole('button', { name: 'relations.action_message' })).toBeNull();
  });

  it.each([
    ['relations.action_message', true],
    ['relations.action_call', false],
    ['relations.action_loop', false],
  ])('%s prefills the composer and never auto-sends', async (label, needsPeer) => {
    useRelationDetail.mockReturnValue({
      detail: detail({ is_peer: needsPeer || undefined }),
      loading: false,
      error: false,
    });
    const { user } = renderPanel();
    await user.click(screen.getByRole('button', { name: label }));

    const href = push.mock.calls[0][0] as string;
    expect(href.startsWith('/fr/dashboard/chat?draft=')).toBe(true);
    // ?intent= is AUTO-SENT (QW-24/ADR-173) — forbidden for anything that
    // reaches another human or places a call.
    expect(href).not.toContain('intent=');
  });
});

describe('RelationDetailPanel — LIA connection block', () => {
  beforeEach(() => {
    push.mockClear();
    useRelationDetail.mockReset();
  });

  const link = (over: Partial<RelationPeerLink> = {}): RelationPeerLink => ({
    connected_since: '2026-06-01T10:00:00Z',
    shared_by_me: [{ domain: 'calendar', level: 'availability' }],
    shared_with_me: [{ domain: 'task', level: 'titles' }],
    ...over,
  });

  it('states both share directions, never just the user’s half', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ is_peer: true, peer_link: link() }),
      loading: false,
      error: false,
    });
    renderPanel();

    expect(screen.getByText('relations.peer_link_title')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.shares.my_title')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.shares.their_title')).toBeInTheDocument();
    expect(
      screen.getByText('settings.peers.shares.badge.calendar_availability')
    ).toBeInTheDocument();
    expect(screen.getByText('settings.peers.shares.badge.task_titles')).toBeInTheDocument();
  });

  it('says plainly when a side shares nothing', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({
        is_peer: true,
        peer_link: link({ shared_by_me: [], shared_with_me: [] }),
      }),
      loading: false,
      error: false,
    });
    renderPanel();
    expect(screen.getByText('relations.peer_link_nothing_shared')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.shares.their_empty')).toBeInTheDocument();
  });

  it('omits the block entirely when there is no connection', () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    renderPanel();
    expect(screen.queryByText('relations.peer_link_title')).toBeNull();
  });

  it('renders without a connection date rather than inventing one', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ is_peer: true, peer_link: link({ connected_since: null }) }),
      loading: false,
      error: false,
    });
    renderPanel();
    expect(screen.getByText('relations.peer_link_title')).toBeInTheDocument();
    expect(screen.queryByText('relations.peer_link_since')).toBeNull();
  });
});

describe('RelationDetailPanel — empty state', () => {
  beforeEach(() => {
    push.mockClear();
    useRelationDetail.mockReset();
  });

  const bare = {
    open_loops: [],
    open_loops_total: 0,
    recent_calls: [],
    recent_calls_total: 0,
    memories: [],
    memories_total: 0,
    peer_messages: [],
    peer_messages_total: 0,
  };

  it('says nothing is tracked when every section is empty', () => {
    useRelationDetail.mockReturnValue({ detail: detail(bare), loading: false, error: false });
    renderPanel();
    expect(screen.getByText('relations.detail_empty')).toBeInTheDocument();
  });

  it('never says "nothing tracked" above a live connection block', () => {
    // The block states since when you are connected and what you share —
    // claiming nothing is tracked would contradict it on the same screen.
    useRelationDetail.mockReturnValue({
      detail: detail({
        ...bare,
        is_peer: true,
        peer_link: { connected_since: null, shared_by_me: [], shared_with_me: [] },
      }),
      loading: false,
      error: false,
    });
    renderPanel();
    expect(screen.getByText('relations.peer_link_title')).toBeInTheDocument();
    expect(screen.queryByText('relations.detail_empty')).toBeNull();
  });
});

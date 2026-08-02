/**
 * Switching from one relationship to another — the production journey.
 *
 * Measured in production on 2026-08-01: the card for **Paul Martin** was
 * opened at 04:49:31, the launch button pressed at 04:49:33, and the chat
 * received *"…sur Marie Dupont"* at 04:49:34. Three times in a row, with three
 * different people on screen.
 *
 * This is a SIMULATION, not a unit test: the real `useRelations` hooks and the
 * real `useApiQuery` run, only the HTTP client is spied on. That is deliberate
 * — the defect lives in the seam between "the panel got a new name" and "the
 * data behind it caught up", which a mocked hook would paper over.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { waitFor } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { push, apiGet, apiPut } = vi.hoisted(() => ({
  push: vi.fn(),
  apiGet: vi.fn(),
  apiPut: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

// Chat deep links are REAL navigations since 2026-08-01 (ADR-192): the App
// Router restored the search params of the entry it already held, so a second
// deep link in a session left with the FIRST one's URL. The oracle is the same
// href — only the door changed.
const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
}));

// The global stub echoes keys, which would make the assertion below blind to
// the very thing it checks — the NAME carried by the intent. This one
// interpolates, exactly as i18next does.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options?.name ? `${key}|name=${String(options.name)}` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('@/lib/api-client', () => ({
  apiClient: { get: apiGet, put: apiPut, post: vi.fn(), delete: vi.fn() },
  default: { get: apiGet, put: apiPut },
  ApiError: class ApiError extends Error {},
}));

import { RelationDetailPanel } from '../RelationDetailPanel';

const SCOPE = {
  sections: ['contact', 'open_loops', 'calls', 'memories', 'peer_messages', 'emails', 'events'],
  directions: ['received', 'sent'],
  roles: ['attendee', 'organizer'],
  max_items: 5,
};

/** A detail payload that ALWAYS names the person the endpoint was asked for. */
function detailFor(name: string) {
  return {
    display_name: name,
    identity_confidence: 'exact',
    open_loops: [],
    open_loops_total: 0,
    recent_calls: [],
    recent_calls_total: 0,
    memories: [],
    memories_total: 0,
    peer_messages: [],
    peer_messages_total: 0,
    peer_link: null,
    is_favorite: false,
    is_peer: false,
  };
}

const EMPTY_SECTION = {
  status: 'empty',
  from_cache: false,
  generated_at: '2026-08-01T04:00:00Z',
  contact: null,
  emails: [],
  events: [],
};

beforeEach(() => {
  openChat.mockReset();
  apiPut.mockReset();
  apiPut.mockResolvedValue(SCOPE);
  apiGet.mockReset();
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === '/relations/overview-scope') return SCOPE;
    if (endpoint.endsWith('/context')) {
      return {
        contact: EMPTY_SECTION,
        emails: EMPTY_SECTION,
        events: EMPTY_SECTION,
        addresses_used: 0,
        window_days: 90,
        email_window_days: 365,
      };
    }
    // `/relations/<name>` — the detail endpoint.
    const name = decodeURIComponent(endpoint.replace('/relations/', ''));
    return detailFor(name);
  });
});

function renderPanel(name: string) {
  return renderWithProviders(
    <RelationDetailPanel
      name={name}
      lng="fr"
      isFavorite={false}
      onToggleFavorite={vi.fn()}
      onBack={vi.fn()}
      candidates={[]}
      onMerged={vi.fn()}
    />
  );
}

/** Open the scope section and press "run" — the only entry point. */
async function runTheOverview(user: ReturnType<typeof renderPanel>['user']) {
  await user.click(screen.getByRole('button', { name: /relations.scope_title/ }));
  await user.click(screen.getByRole('button', { name: /relations.scope_launch/ }));
}

describe('switching relationship then running a 360°', () => {
  it('asks the API for the NEW person the panel was given', async () => {
    const { rerender } = renderPanel('Marie Dupont');
    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith('/relations/Marie%20Dupont', expect.anything())
    );

    rerender(
      <RelationDetailPanel
        name="Paul Martin"
        lng="fr"
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onBack={vi.fn()}
      candidates={[]}
      onMerged={vi.fn()}
      />
    );

    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith('/relations/Paul%20Martin', expect.anything())
    );
  });

  it('sends the SECOND person to the chat, never the first', async () => {
    const { user, rerender } = renderPanel('Marie Dupont');
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Marie Dupont' })).toBeInTheDocument()
    );

    rerender(
      <RelationDetailPanel
        name="Paul Martin"
        lng="fr"
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onBack={vi.fn()}
      candidates={[]}
      onMerged={vi.fn()}
      />
    );
    // The header must show the person the panel was asked about — if it still
    // shows the previous one, the intent built from it is wrong too.
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Paul Martin' })).toBeInTheDocument()
    );

    await runTheOverview(user);

    await waitFor(() => expect(openChat).toHaveBeenCalledTimes(1));
    // The INTENT specifically, not the whole href: since ADR-191 the link also
    // carries `subject=`, so asserting on the href would pass on the subject
    // alone even if the sentence named the wrong person — the very defect this
    // test exists to catch.
    const intent = new URLSearchParams(String(openChat.mock.calls[0][0]).split('?')[1]).get('intent');
    expect(intent).toContain('Paul Martin');
    expect(intent).not.toContain('Marie Dupont');
  });

  it('carries the capability directive for the person on screen (ADR-191)', async () => {
    // Prose alone reaches the planner as a suggestion. Measured in production
    // on 2026-08-01: the 360° tool scored 0.853, the best of the whole
    // catalogue, and the plan called the generic mail tool instead. The
    // directive is what makes the capability certain — and its subject must be
    // the name the panel is displaying, not the one it mounted with.
    const { user, rerender } = renderPanel('Marie Dupont');
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Marie Dupont' })).toBeInTheDocument()
    );

    rerender(
      <RelationDetailPanel
        name="Paul Martin"
        lng="fr"
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onBack={vi.fn()}
      candidates={[]}
      onMerged={vi.fn()}
      />
    );
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Paul Martin' })).toBeInTheDocument()
    );

    await runTheOverview(user);

    await waitFor(() => expect(openChat).toHaveBeenCalledTimes(1));
    const query = new URLSearchParams(String(openChat.mock.calls[0][0]).split('?')[1]);
    expect(query.get('capability')).toBe('person_overview');
    expect(query.get('subject')).toBe('Paul Martin');
  });

  it('saves the scope BEFORE the directive can be acted on', async () => {
    // The tool reads the stored scope server-side; navigating first would race
    // the write, and the guaranteed call would run on the PREVIOUS selection
    // with nothing on screen saying so.
    const { user } = renderPanel('Marie Dupont');
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Marie Dupont' })).toBeInTheDocument()
    );

    await runTheOverview(user);

    await waitFor(() => expect(openChat).toHaveBeenCalledTimes(1));
    expect(apiPut.mock.calls[0][0]).toBe('/relations/overview-scope');
    expect(apiPut.mock.invocationCallOrder[0]).toBeLessThan(openChat.mock.invocationCallOrder[0]);
  });

  it('never offers the button while the panel still holds the previous person', async () => {
    // The window that matters: between "the name changed" and "the data caught
    // up", the panel must not present an actionable card built on stale data.
    const { rerender } = renderPanel('Marie Dupont');
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Marie Dupont' })).toBeInTheDocument()
    );

    let slow: (value: unknown) => void = () => undefined;
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint === '/relations/overview-scope') return SCOPE;
      if (endpoint.endsWith('/context')) return new Promise(() => undefined);
      return new Promise(resolve => {
        slow = resolve;
      });
    });

    rerender(
      <RelationDetailPanel
        name="Paul Martin"
        lng="fr"
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onBack={vi.fn()}
      candidates={[]}
      onMerged={vi.fn()}
      />
    );

    // While the new detail is in flight, the OLD name must not be on screen.
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Marie Dupont' })).not.toBeInTheDocument()
    );
    slow(detailFor('Paul Martin'));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Paul Martin' })).toBeInTheDocument()
    );
  });
});

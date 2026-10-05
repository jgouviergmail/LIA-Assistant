/**
 * The dashboard shell must not mount for an account that is not active.
 *
 * The layout already redirects such an account to /account-inactive, but it does
 * so from an effect — and until that client-side navigation completes it still
 * RENDERS its children. That window is not free: the shell mounts the broadcast
 * provider and the navbar, which each open an EventSource on
 * /api/v1/notifications/stream, plus the pages' polling hooks and the avatar
 * proxy.
 *
 * EventSource cannot read an HTTP status: a 403 surfaces as a bare `onerror`,
 * which the hook treats as a dropped connection and retries five times. A
 * permanent verdict is therefore replayed as if it were a network blip.
 *
 * Measured in production over 7 days (2026-07-29 → 2026-08-05), for five
 * accounts that were verified but not yet activated — one of them 225 times in a
 * single day::
 *
 *     /api/v1/notifications/stream        82
 *     /api/v1/agents/runs/active          57
 *     /api/v1/auth/profile-image-proxy    56
 *     /api/v1/notifications/broadcasts/unread  40
 *     /api/v1/personalities               35
 *
 * Four of those five accounts were created in the three days before the
 * measurement, so this is the standard sign-up path, not an edge case: the
 * newcomer sees an application that looks broken while the server refuses every
 * one of its calls.
 *
 * Not rendering the shell closes all of them at once — a component that never
 * mounts cannot poll.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type { ConnectorHealthResponse, ConnectorHealthSettings } from '@/hooks/useConnectorHealth';
import type { AvatarConfig } from '@/lib/avatars/types';
import type { PersonalityListResponse, UserPersonalityResponse } from '@/types/personality';
import { usePersonalityStore } from '@/stores/personalityStore';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/fr/dashboard',
  useSearchParams: () => new URLSearchParams(),
}));

// The two components that open an EventSource as soon as the shell mounts.
// Spying on them is the whole point: the assertion is that they never render.
const { broadcastProviderSpy, broadcastModalSpy } = vi.hoisted(() => ({
  broadcastProviderSpy: vi.fn(),
  broadcastModalSpy: vi.fn(),
}));
vi.mock('@/lib/broadcast', () => ({
  BroadcastProvider: ({ children }: { children: React.ReactNode }) => {
    broadcastProviderSpy();
    return <>{children}</>;
  },
  useBroadcast: () => ({ unreadCount: 0, broadcasts: [] }),
}));
vi.mock('@/components/broadcast/BroadcastModal', () => ({
  BroadcastModal: () => {
    broadcastModalSpy();
    return null;
  },
}));

import DashboardLayout from '../layout';

const ACTIVE_USER = {
  id: 'u1',
  email: 'someone@example.org',
  is_active: true,
  onboarding_completed: true,
};
const PENDING_USER = { ...ACTIVE_USER, is_active: false };

const CHILD_MARKER = 'dashboard-child-content';

// Exercise the real child queries against controlled successful responses.
// A layout test must not open a real stream or issue an unhandled host fetch.
const responses = new Map<string, unknown>([
  [
    '/api/v1/config',
    {
      sse: { heartbeat_interval_seconds: 30 },
      rate_limits: { enabled: false, per_minute: 60, burst: 10 },
      i18n: { supported_languages: ['fr'], default_language: 'fr' },
      features: {
        tool_approval_enabled: false,
        attachments_enabled: false,
        rag_spaces_enabled: false,
        rag_spaces_embedding_model: 'test',
        journals_enabled: false,
        meetings_enabled: false,
        radio_enabled: false,
        live_enabled: false,
      },
      api_version: 'test',
    } satisfies AppConfig,
  ],
  [
    '/api/v1/avatars/config',
    {
      available: false,
      enabled: false,
      connected: false,
      face_id: null,
      connector_version: null,
      session_length_seconds: 300,
      connect_timeout_seconds: 10,
    } satisfies AvatarConfig,
  ],
  [
    '/api/v1/connectors/health/settings',
    {
      polling_interval_ms: 60000,
      critical_cooldown_ms: 60000,
    } satisfies ConnectorHealthSettings,
  ],
  [
    '/api/v1/connectors/health',
    {
      connectors: [],
      has_issues: false,
      critical_count: 0,
      warning_count: 0,
      checked_at: '2026-10-05T08:00:00Z',
    } satisfies ConnectorHealthResponse,
  ],
  ['/api/v1/personalities', { personalities: [], count: 0 } satisfies PersonalityListResponse],
  [
    '/api/v1/personalities/current',
    {
      personality_id: null,
      personality: null,
    } satisfies UserPersonalityResponse,
  ],
  ['/api/v1/agents/runs/active', { active: false }],
]);

class FakeEventSource extends EventTarget {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  constructor(
    readonly url: string,
    readonly options?: EventSourceInit
  ) {
    super();
    FakeEventSource.instances.push(this);
  }
}

async function renderLayout() {
  // Async route params and the shell's initial API reads must settle before
  // asserting that a redirect kept every stream-opening child unmounted.
  return act(async () =>
    renderWithProviders(
      <DashboardLayout params={Promise.resolve({ lng: 'fr' })}>
        <div data-testid={CHILD_MARKER} />
      </DashboardLayout>
    )
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  usePersonalityStore.getState().reset();
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const endpoint = new URL(String(input), 'http://localhost').pathname;
      if (!responses.has(endpoint)) throw new Error(`Unexpected API read: ${endpoint}`);
      return Response.json(responses.get(endpoint));
    })
  );
});

afterEach(() => vi.unstubAllGlobals());

describe('Dashboard shell — account awaiting activation', () => {
  it('does not render the shell while the redirect is in flight', async () => {
    useAuth.mockReturnValue({ user: PENDING_USER, isLoading: false, logout: vi.fn() });

    await renderLayout();

    expect(screen.queryByTestId(CHILD_MARKER)).not.toBeInTheDocument();
  });

  it('never mounts the components that open a notifications stream', async () => {
    useAuth.mockReturnValue({ user: PENDING_USER, isLoading: false, logout: vi.fn() });

    await renderLayout();

    // Each of these opens an EventSource on /notifications/stream, and a 403
    // reaches onerror without a status — so the hook retries it five times.
    expect(broadcastProviderSpy).not.toHaveBeenCalled();
    expect(broadcastModalSpy).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('still sends the account to the page that explains the situation', async () => {
    useAuth.mockReturnValue({ user: PENDING_USER, isLoading: false, logout: vi.fn() });

    await renderLayout();

    expect(push).toHaveBeenCalledWith(expect.stringContaining('account-inactive'));
  });
});

describe('Dashboard shell — active account', () => {
  it('renders the shell and its children', async () => {
    useAuth.mockReturnValue({ user: ACTIVE_USER, isLoading: false, logout: vi.fn() });

    const { unmount } = await renderLayout();

    expect(screen.getByTestId(CHILD_MARKER)).toBeInTheDocument();
    expect(broadcastProviderSpy).toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
    unmount();
    expect(FakeEventSource.instances[0].close).toHaveBeenCalledOnce();
  });

  it("paints the landing's cosmos as the page ground, under an opaque header", async () => {
    useAuth.mockReturnValue({ user: ACTIVE_USER, isLoading: false, logout: vi.fn() });

    await renderLayout();

    // The cosmos layers are fixed on a negative z-index of the root stacking
    // context: any in-flow background between them and <body> would cover them.
    const cosmos = screen.getByTestId('app-cosmos');
    expect(cosmos).toHaveClass('cosmos');
    for (let el = cosmos.parentElement; el && el !== document.body; el = el.parentElement) {
      expect(el.className).not.toMatch(/(^|\s)bg-/);
    }
    // Nor does the shell wrap the page in a panel of its own: the pages' panels
    // and cards are the only opaque surfaces, so the cosmos shows around them.
    for (
      let el = screen.getByTestId(CHILD_MARKER).parentElement;
      el && el !== document.body;
      el = el.parentElement
    ) {
      expect(el.className).not.toMatch(/(^|\s)bg-/);
    }
    expect(screen.getByRole('banner')).toHaveClass('bg-background');
  });

  it('does not redirect an active account', async () => {
    useAuth.mockReturnValue({ user: ACTIVE_USER, isLoading: false, logout: vi.fn() });

    await renderLayout();

    expect(push).not.toHaveBeenCalled();
  });
});

describe('Dashboard shell — signed out', () => {
  it('renders nothing and sends the visitor to the login page', async () => {
    useAuth.mockReturnValue({ user: null, isLoading: false, logout: vi.fn() });

    await renderLayout();

    expect(screen.queryByTestId(CHILD_MARKER)).not.toBeInTheDocument();
    expect(broadcastProviderSpy).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith(expect.stringContaining('login'));
  });
});

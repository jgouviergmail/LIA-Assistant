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

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

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

function renderLayout() {
  return renderWithProviders(
    <DashboardLayout params={Promise.resolve({ lng: 'fr' })}>
      <div data-testid={CHILD_MARKER} />
    </DashboardLayout>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Dashboard shell — account awaiting activation', () => {
  it('does not render the shell while the redirect is in flight', () => {
    useAuth.mockReturnValue({ user: PENDING_USER, isLoading: false, logout: vi.fn() });

    renderLayout();

    expect(screen.queryByTestId(CHILD_MARKER)).not.toBeInTheDocument();
  });

  it('never mounts the components that open a notifications stream', () => {
    useAuth.mockReturnValue({ user: PENDING_USER, isLoading: false, logout: vi.fn() });

    renderLayout();

    // Each of these opens an EventSource on /notifications/stream, and a 403
    // reaches onerror without a status — so the hook retries it five times.
    expect(broadcastProviderSpy).not.toHaveBeenCalled();
    expect(broadcastModalSpy).not.toHaveBeenCalled();
  });

  it('still sends the account to the page that explains the situation', () => {
    useAuth.mockReturnValue({ user: PENDING_USER, isLoading: false, logout: vi.fn() });

    renderLayout();

    expect(push).toHaveBeenCalledWith(expect.stringContaining('account-inactive'));
  });
});

describe('Dashboard shell — active account', () => {
  it('renders the shell and its children', () => {
    useAuth.mockReturnValue({ user: ACTIVE_USER, isLoading: false, logout: vi.fn() });

    renderLayout();

    expect(screen.getByTestId(CHILD_MARKER)).toBeInTheDocument();
    expect(broadcastProviderSpy).toHaveBeenCalled();
  });

  it('does not redirect an active account', () => {
    useAuth.mockReturnValue({ user: ACTIVE_USER, isLoading: false, logout: vi.fn() });

    renderLayout();

    expect(push).not.toHaveBeenCalled();
  });
});

describe('Dashboard shell — signed out', () => {
  it('renders nothing and sends the visitor to the login page', () => {
    useAuth.mockReturnValue({ user: null, isLoading: false, logout: vi.fn() });

    renderLayout();

    expect(screen.queryByTestId(CHILD_MARKER)).not.toBeInTheDocument();
    expect(broadcastProviderSpy).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith(expect.stringContaining('login'));
  });
});

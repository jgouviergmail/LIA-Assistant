/**
 * Settings page — the master-detail shell, integrated.
 *
 * The pieces are unit-tested on their own (model, rail, overview, pane); what
 * only the page can prove is the ORCHESTRATION: the overview is the landing,
 * a rail pick opens exactly one section and writes `?section=` so the URL
 * stays shareable, a `?section=` arrival opens the pane directly, and the
 * back path returns to the overview with a clean URL.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

import SettingsPage from '../page';

// The portrait shortcut is unit-tested on its own; here it would only fetch
// `/journals/portrait` into the void and pollute stderr.
vi.mock('@/hooks/useJournalPortrait', () => ({
  useJournalPortrait: () => ({ hasPortrait: false }),
}));

const authState = vi.hoisted(() => ({
  user: { id: 'u1', email: 'u@example.test', is_superuser: false } as {
    id: string;
    email: string;
    is_superuser: boolean;
  } | null,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: authState.user }),
}));

const navState = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/en/dashboard/settings',
  useSearchParams: () => navState.params,
}));

vi.mock('@/hooks/useDebugPanelEnabled', () => ({
  useDebugPanelEnabled: () => ({ userAccessAvailable: false }),
}));

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: {
      features: { open_loops_enabled: true, habits_enabled: true, peers_enabled: true },
    },
  }),
}));

function renderPage() {
  return renderWithProviders(<SettingsPage params={Promise.resolve({ lng: 'en' })} />);
}

describe('Settings page — master-detail shell', () => {
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    window.history.replaceState({}, '', '/en/dashboard/settings');
    navState.params = new URLSearchParams();
    authState.user = { id: 'u1', email: 'u@example.test', is_superuser: false };
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lands on the overview with the rail alongside', async () => {
    renderPage();
    expect(
      await screen.findByRole('navigation', { name: 'settings.shell.nav_label' })
    ).toBeInTheDocument();
    // Overview cards carry descriptions; the rail does not.
    expect(screen.getByText('settings.theme.description')).toBeInTheDocument();
    // No section pane is mounted.
    expect(document.querySelector('[id^="settings-section-"]')).toBeNull();
  });

  it('opens the picked section and records it in the URL', async () => {
    const { user } = renderPage();
    const nav = await screen.findByRole('navigation', { name: 'settings.shell.nav_label' });
    await user.click(
      within(nav).getByRole('button', { name: /settings\.chat_shortcuts\.title/ })
    );

    await waitFor(() => {
      expect(document.querySelector('#settings-section-chat-shortcuts')).not.toBeNull();
    });
    expect(window.location.search).toBe('?section=chat-shortcuts');
    // The overview is gone; the rail stays.
    expect(screen.queryByText('settings.theme.description')).not.toBeInTheDocument();
    expect(nav).toBeInTheDocument();
  });

  it('resolves a ?section= arrival straight into the pane', async () => {
    navState.params = new URLSearchParams('section=voice-mode');
    renderPage();
    await waitFor(() => {
      expect(document.querySelector('#settings-section-voice-mode')).not.toBeNull();
    });
  });

  it('ignores an unknown ?section= token and lands on the overview', async () => {
    navState.params = new URLSearchParams('section=does-not-exist');
    renderPage();
    expect(await screen.findByText('settings.theme.description')).toBeInTheDocument();
    expect(document.querySelector('[id^="settings-section-"]')).toBeNull();
  });

  it('returns to the overview with a clean URL', async () => {
    const { user } = renderPage();
    const nav = await screen.findByRole('navigation', { name: 'settings.shell.nav_label' });
    await user.click(
      within(nav).getByRole('button', { name: /settings\.chat_shortcuts\.title/ })
    );
    await waitFor(() => {
      expect(document.querySelector('#settings-section-chat-shortcuts')).not.toBeNull();
    });

    await user.click(screen.getByRole('button', { name: /settings\.shell\.back/ }));
    expect(await screen.findByText('settings.theme.description')).toBeInTheDocument();
    expect(window.location.search).toBe('');
  });

  it('closes the pane when a router navigation lands on the bare settings URL', async () => {
    // On `?section=theme`, clicking "Settings" in the dashboard nav pushes the
    // bare URL: the pane must yield back to the overview, or the nav entry
    // silently does nothing.
    navState.params = new URLSearchParams('section=theme');
    const { rerender } = renderPage();
    await waitFor(() => {
      expect(document.querySelector('#settings-section-theme')).not.toBeNull();
    });

    navState.params = new URLSearchParams();
    rerender(<SettingsPage params={Promise.resolve({ lng: 'en' })} />);

    expect(await screen.findByText('settings.theme.description')).toBeInTheDocument();
    expect(document.querySelector('[id^="settings-section-"]')).toBeNull();
  });

  it('shows the administration rail entries to a superuser', async () => {
    authState.user = { id: 'u1', email: 'u@example.test', is_superuser: true };
    renderPage();
    const nav = await screen.findByRole('navigation', { name: 'settings.shell.nav_label' });
    expect(
      within(nav).getByRole('button', { name: /settings\.admin\.users\.title/ })
    ).toBeInTheDocument();
  });
});

/**
 * The operator's switch over the public demonstrator link.
 *
 * "Take the demo offline" is the most urgent action an operator can need, so
 * the control must be one click away — and must never lie. Two states a
 * screenshot cannot tell apart and this file can:
 *
 * - the switch is ON and a URL is deployed → the link is live;
 * - the switch is ON and NO URL is deployed → nothing is shown to anyone, and
 *   the card must say so instead of implying a live link.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The section shell is an Accordion item; it needs a provider this unit does
// not care about. Its own tests cover the shell.
vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const query = vi.fn();
const mutate = vi.fn();
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: (...a: unknown[]) => query(...a) }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false }),
}));

import AdminPublicDemoLinkSection from '@/components/settings/AdminPublicDemoLinkSection';

interface View {
  enabled: boolean;
  url: string | null;
  url_configured: boolean;
}

function mockView(view: View, loading = false): void {
  query.mockReturnValue({ data: view, loading, setData: vi.fn() });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AdminPublicDemoLinkSection', () => {
  it('reads the switch from the admin endpoint', () => {
    mockView({ enabled: false, url: null, url_configured: true });
    render(<AdminPublicDemoLinkSection lng="fr" />);
    expect(String(query.mock.calls[0][0])).toBe('/admin/public-demo-link');
  });

  it('shows the switch off by default, and no link', () => {
    mockView({ enabled: false, url: null, url_configured: true });
    render(<AdminPublicDemoLinkSection lng="fr" />);

    const control = screen.getByRole('switch');
    expect(control).not.toBeChecked();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows where the link points once it is live', () => {
    mockView({ enabled: true, url: 'https://demo.example.org', url_configured: true });
    render(<AdminPublicDemoLinkSection lng="fr" />);

    expect(screen.getByRole('switch')).toBeChecked();
    // An operator must be able to check the destination without guessing it.
    expect(screen.getByRole('link', { name: /demo\.example\.org/ })).toHaveAttribute(
      'href',
      'https://demo.example.org'
    );
  });

  it('says nothing is deployed rather than offering an inert switch', () => {
    mockView({ enabled: false, url: null, url_configured: false });
    render(<AdminPublicDemoLinkSection lng="fr" />);

    // The switch would flip a setting that shows nothing: the card states the
    // deployment fact instead of letting the operator believe it worked.
    expect(
      screen.getByText('settings.admin.publicDemoLink.notDeployed')
    ).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('flips the switch through the admin endpoint', async () => {
    mockView({ enabled: false, url: null, url_configured: true });
    mutate.mockResolvedValue({ enabled: true, url: 'https://demo.example.org', url_configured: true });
    render(<AdminPublicDemoLinkSection lng="fr" />);

    await userEvent.click(screen.getByRole('switch'));

    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(mutate).toHaveBeenCalledWith('/admin/public-demo-link', { enabled: true });
  });

  it('keeps a name a screen reader can act on', () => {
    mockView({ enabled: false, url: null, url_configured: true });
    render(<AdminPublicDemoLinkSection lng="fr" />);
    expect(screen.getByRole('switch')).toHaveAccessibleName(
      'settings.admin.publicDemoLink.switchLabel'
    );
  });
});

/**
 * Admin panel for the instance capability switches.
 *
 * The one thing this panel must never do is let an operator believe a switch
 * took effect when it did not. So it shows three separate facts per
 * capability — what was set, what the deployment permits, what actually
 * applies — and makes an inert switch unmistakable rather than merely
 * greyed out.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const apiGet = vi.fn();
const apiMutate = vi.fn();

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (...args: unknown[]) => apiGet(...args),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: apiMutate, loading: false }),
}));

vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import AdminCapabilitiesSection from '@/components/settings/AdminCapabilitiesSection';
import type { CapabilitySwitch } from '@/components/settings/AdminCapabilitiesSection';

function capability(overrides: Partial<CapabilitySwitch> = {}): CapabilitySwitch {
  return {
    capability: 'image_generation',
    label_key: 'capabilities.items.image_generation',
    switch_enabled: true,
    deployment_available: true,
    effective_enabled: true,
    enforced_in_catalogue: true,
    enforced_on_routes: true,
    updated_by: null,
    updated_at: null,
    is_default: true,
    ...overrides,
  };
}

function mockList(rows: CapabilitySwitch[], loading = false): void {
  apiGet.mockReturnValue({ data: rows, loading, setData: vi.fn() });
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMutate.mockResolvedValue(capability({ switch_enabled: false, effective_enabled: false }));
});

describe('AdminCapabilitiesSection', () => {
  it('renders one labelled switch per capability', async () => {
    mockList([
      capability(),
      capability({ capability: 'browser', label_key: 'capabilities.items.browser' }),
    ]);

    render(<AdminCapabilitiesSection lng="fr" />);

    const switches = await screen.findAllByRole('switch');
    expect(switches).toHaveLength(2);
    // Each control carries its own translated accessible name.
    expect(
      screen.getByRole('switch', { name: 'capabilities.items.image_generation' })
    ).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'capabilities.items.browser' })).toBeInTheDocument();
  });

  it('reflects the stored state of each switch', async () => {
    mockList([
      capability({ switch_enabled: true }),
      capability({
        capability: 'browser',
        label_key: 'capabilities.items.browser',
        switch_enabled: false,
        effective_enabled: false,
      }),
    ]);

    render(<AdminCapabilitiesSection lng="fr" />);

    const on = await screen.findByRole('switch', {
      name: 'capabilities.items.image_generation',
    });
    const off = screen.getByRole('switch', { name: 'capabilities.items.browser' });
    expect(on).toBeChecked();
    expect(off).not.toBeChecked();
  });

  it('marks a capability the deployment forbids and refuses to toggle it', async () => {
    const user = userEvent.setup();
    mockList([
      capability({
        capability: 'telephony',
        label_key: 'capabilities.items.telephony',
        switch_enabled: true,
        deployment_available: false,
        effective_enabled: false,
      }),
    ]);

    render(<AdminCapabilitiesSection lng="fr" />);

    // Said explicitly, not just greyed out: the operator learns WHY.
    expect(
      await screen.findByText('settings.admin.capabilities.unavailableBadge')
    ).toBeInTheDocument();
    expect(
      screen.getByText('settings.admin.capabilities.deploymentBlocked')
    ).toBeInTheDocument();

    const control = screen.getByRole('switch', { name: 'capabilities.items.telephony' });
    expect(control).toBeDisabled();
    await user.click(control);
    // Flipping it would change a stored value that changes nothing.
    expect(apiMutate).not.toHaveBeenCalled();
  });

  it('sends the new state to the capability endpoint', async () => {
    const user = userEvent.setup();
    mockList([capability()]);

    render(<AdminCapabilitiesSection lng="fr" />);

    await user.click(await screen.findByRole('switch'));

    await waitFor(() => expect(apiMutate).toHaveBeenCalled());
    expect(apiMutate.mock.calls[0][0]).toBe('/admin/capabilities/image_generation');
    expect(apiMutate.mock.calls[0][1]).toEqual({ enabled: false });
  });

  it('explains where each switch is enforced', async () => {
    mockList([
      capability({ enforced_in_catalogue: true, enforced_on_routes: false }),
      capability({
        capability: 'attachments',
        label_key: 'capabilities.items.attachments',
        enforced_in_catalogue: false,
        enforced_on_routes: true,
      }),
    ]);

    render(<AdminCapabilitiesSection lng="fr" />);

    // An operator should not have to guess what "off" will actually do.
    expect(
      await screen.findByText('settings.admin.capabilities.enforcedCatalogue')
    ).toBeInTheDocument();
    expect(screen.getByText('settings.admin.capabilities.enforcedRoutes')).toBeInTheDocument();
  });

  it('shows skeletons on first load, not an empty list', async () => {
    mockList([], true);

    const { container } = render(<AdminCapabilitiesSection lng="fr" />);

    // A blank panel reads as "no capabilities"; a busy one reads as loading.
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(screen.queryAllByRole('switch')).toHaveLength(0);
  });

  it('keeps each row self-contained so a long list stays readable', async () => {
    mockList([capability(), capability({ capability: 'browser', label_key: 'capabilities.items.browser' })]);

    render(<AdminCapabilitiesSection lng="fr" />);

    const first = (await screen.findAllByRole('switch'))[0];
    const row = first.closest('div.rounded-lg');
    expect(row).not.toBeNull();
    // Label, description and control travel together — the responsive layout
    // stacks them on phones and puts the switch on the right from `sm` up.
    expect(within(row as HTMLElement).getByRole('switch')).toBe(first);
  });
});

/**
 * Twenty-five switches, grouped (B7, lot 8).
 *
 * The panel listed twelve capabilities in one column. With the thirteen that
 * shipped without a switch it holds twenty-five, and a single column of
 * twenty-five identical rows is a wall an operator scrolls past rather than
 * reads. Grouped by family, the panel answers « what can this instance do »
 * section by section.
 *
 * Two claims it must keep making correctly:
 *
 * - **a family nobody declared still draws its rows.** A capability whose
 *   family the frontend cannot name must never vanish from the panel — an
 *   invisible switch is worse than an ugly one.
 * - **where a switch BITES is stated honestly.** Five capabilities are
 *   enforced at a service chokepoint, not on a route, and the panel used to
 *   fold both into « enforced on routes ».
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const apiGet = vi.fn();
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (...args: unknown[]) => apiGet(...args),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn(), loading: false }),
}));
vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import AdminCapabilitiesSection from '@/components/settings/AdminCapabilitiesSection';
import type { CapabilitySwitch } from '@/components/settings/AdminCapabilitiesSection';

function capability(overrides: Partial<CapabilitySwitch> = {}): CapabilitySwitch {
  const name = overrides.capability ?? 'image_generation';
  return {
    capability: name,
    // Derived, never a fixed literal: a factory whose label ignores the
    // capability makes every « this row is here » assertion vacuous.
    label_key: `capabilities.items.${name}`,
    switch_enabled: true,
    deployment_available: true,
    effective_enabled: true,
    enforced_in_catalogue: true,
    enforced_on_routes: true,
    enforced_in_service: false,
    family: 'media',
    updated_by: null,
    updated_at: null,
    is_default: true,
    ...overrides,
  };
}

function mount(rows: CapabilitySwitch[]) {
  apiGet.mockReturnValue({ data: rows, loading: false, setData: vi.fn() });
  return render(<AdminCapabilitiesSection lng="en" />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the panel groups its switches', () => {
  it('draws one region per family, in a stable order', () => {
    mount([
      capability({ capability: 'workboard', family: 'work' }),
      capability({ capability: 'stt', family: 'media' }),
      capability({ capability: 'memory', family: 'knowledge' }),
    ]);

    const regions = screen.getAllByRole('group');
    // The order is the declaration's, never the payload's: an operator who
    // switches something must find the panel where they left it.
    expect(regions.map(region => region.getAttribute('data-family'))).toEqual([
      'media',
      'knowledge',
      'work',
    ]);
  });

  it('puts every switch in its own family', () => {
    mount([
      capability({ capability: 'workboard', family: 'work' }),
      capability({ capability: 'stt', family: 'media' }),
    ]);

    const work = screen.getByRole('group', { name: /families.work/ });
    expect(within(work).getByLabelText(/capabilities.items.workboard/)).toBeInTheDocument();
    expect(within(work).queryByLabelText(/capabilities.items.stt/)).not.toBeInTheDocument();
  });

  it('draws no region for a family this instance has nothing in', () => {
    mount([capability({ capability: 'stt', family: 'media' })]);

    expect(screen.queryByRole('group', { name: /families.people/ })).not.toBeInTheDocument();
  });

  it('still draws a switch whose family nobody declared', () => {
    // An invisible switch is worse than an ugly one: an operator who cannot
    // see it cannot turn it off.
    mount([capability({ capability: 'mystery', family: 'not_a_family' })]);

    expect(screen.getByLabelText(/capabilities.items.mystery/)).toBeInTheDocument();
    // Drawn LAST, after every declared family, rather than dropped.
    expect(screen.getByRole('group').getAttribute('data-family')).toBe('not_a_family');
  });
});

describe('where a switch bites is stated honestly', () => {
  it('says « service » for a chokepoint, not « routes »', () => {
    mount([
      capability({
        capability: 'memory',
        family: 'knowledge',
        enforced_in_catalogue: false,
        enforced_on_routes: false,
        enforced_in_service: true,
      }),
    ]);

    expect(screen.getByText(/enforcedService/)).toBeInTheDocument();
    expect(screen.queryByText(/enforcedRoutes/)).not.toBeInTheDocument();
  });

  it('says « routes » for a route guard', () => {
    mount([
      capability({
        capability: 'workboard',
        family: 'work',
        enforced_in_catalogue: false,
        enforced_on_routes: true,
        enforced_in_service: false,
      }),
    ]);

    expect(screen.getByText(/enforcedRoutes/)).toBeInTheDocument();
  });

  it('says both when a capability removes agents AND guards routes', () => {
    mount([
      capability({
        capability: 'telephony',
        family: 'media',
        enforced_in_catalogue: true,
        enforced_on_routes: true,
      }),
    ]);

    expect(screen.getByText(/enforcedBoth/)).toBeInTheDocument();
  });

  it('says the deployment blocks it, whatever the enforcement', () => {
    mount([capability({ capability: 'telephony', deployment_available: false })]);

    expect(screen.getByText(/deploymentBlocked/)).toBeInTheDocument();
  });
});

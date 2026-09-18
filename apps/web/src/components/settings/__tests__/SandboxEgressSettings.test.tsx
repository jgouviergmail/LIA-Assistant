/**
 * SandboxEgressSettings (ADR-298) — the flag gate, the two lists, the one edit
 * (with or without the turn's data), the revoke, the stated cut and the
 * capacity gauge. The i18n stub echoes keys, so controls are addressed by key.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { EgressGrant, ReachableHost } from '@/types/sandbox-egress';

const setScope = vi.fn(async () => true);
const revoke = vi.fn(async () => true);
const refetch = vi.fn();
const state = {
  flagOn: true,
  unavailable: false,
  loadError: false,
  reachable: [] as ReachableHost[],
  askEnabled: true as boolean | null,
  grants: [] as EgressGrant[],
  total: 0,
  maxPerUser: 50,
};

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { python_sandbox_egress_enabled: state.flagOn } },
  }),
}));
vi.mock('@/hooks/useSandboxEgress', () => ({
  useSandboxEgress: () => ({
    reachable: state.reachable,
    askEnabled: state.askEnabled,
    grants: state.grants,
    total: state.total,
    maxPerUser: state.maxPerUser,
    loading: false,
    unavailable: state.unavailable,
    loadError: state.loadError,
    refetch,
    setScope,
    revoke,
  }),
}));

import { SandboxEgressSettings } from '../SandboxEgressSettings';

function grant(over: Partial<EgressGrant> = {}): EgressGrant {
  return {
    id: 'g-1',
    host: 'status.example.org',
    share_turn_data: true,
    created_at: '2026-09-18T08:00:00Z',
    last_used_at: null,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.flagOn = true;
  state.unavailable = false;
  state.loadError = false;
  state.askEnabled = true;
  state.reachable = [
    { host: 'api.search.brave.com', status: 'connector', connector: 'brave_search' },
    { host: 'api.example.org', status: 'operator', connector: null },
  ];
  state.grants = [grant(), grant({ id: 'g-2', host: 'feeds.example.net', share_turn_data: false })];
  state.total = 2;
  state.maxPerUser = 50;
});

const renderSection = () => render(<SandboxEgressSettings lng="fr" />);

describe('SandboxEgressSettings — gates', () => {
  it('renders nothing when the instance flag is off', () => {
    state.flagOn = false;
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the surface is unavailable', () => {
    state.unavailable = true;
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it('offers a retry on a transient failure, never a vanished section', () => {
    state.loadError = true;
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: /common\.retry/ }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe('SandboxEgressSettings — reachable without asking', () => {
  it('lists connector hosts with their brand name and operator hosts', () => {
    renderSection();
    expect(screen.getByText('api.search.brave.com')).toBeInTheDocument();
    expect(screen.getByText('api.example.org')).toBeInTheDocument();
    expect(screen.getByText('settings.sandbox_egress.source_connector')).toBeInTheDocument();
    expect(screen.getByText('settings.sandbox_egress.source_operator')).toBeInTheDocument();
  });

  it('says so when nothing is reachable', () => {
    state.reachable = [];
    renderSection();
    expect(screen.getByText('settings.sandbox_egress.reachable_empty')).toBeInTheDocument();
  });

  it('states when the instance refuses unknown hosts instead of asking', () => {
    state.askEnabled = false;
    renderSection();
    expect(screen.getByText('settings.sandbox_egress.ask_disabled')).toBeInTheDocument();
  });

  it('says nothing about refusal while the answer is in flight or asking is on', () => {
    renderSection();
    expect(screen.queryByText('settings.sandbox_egress.ask_disabled')).not.toBeInTheDocument();
  });
});

describe('SandboxEgressSettings — permissions', () => {
  it('draws each grant with its scope switch reflecting the stored decision', () => {
    renderSection();
    const switches = screen.getAllByRole('switch');
    expect(switches).toHaveLength(2);
    expect(switches[0]).toHaveAttribute('aria-checked', 'true');
    expect(switches[1]).toHaveAttribute('aria-checked', 'false');
  });

  it('changes the scope through the hook', async () => {
    renderSection();
    fireEvent.click(screen.getAllByRole('switch')[0]);
    await waitFor(() => expect(setScope).toHaveBeenCalledWith('g-1', false));
  });

  it('revokes a grant through the hook, from a row menu named with its host', async () => {
    renderSection();
    expect(
      screen.getAllByRole('button', { name: 'settings.sandbox_egress.row_menu' })
    ).toHaveLength(2);
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.sandbox_egress.revoke' })[1]);
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('g-2'));
  });

  it('shows the empty state when nothing was granted yet', () => {
    state.grants = [];
    state.total = 0;
    renderSection();
    expect(screen.getByText('settings.sandbox_egress.grants_empty')).toBeInTheDocument();
  });

  it('states the cut when the exact total exceeds the page', () => {
    state.total = 5;
    renderSection();
    expect(screen.getByText('settings.sandbox_egress.grants_not_shown')).toBeInTheDocument();
  });

  it('draws the capacity against the published cap', () => {
    renderSection();
    const gauge = screen.getByRole('progressbar');
    expect(gauge).toHaveAttribute('aria-valuenow', '2');
    expect(gauge).toHaveAttribute('aria-valuemax', '50');
  });
});

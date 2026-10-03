/**
 * SandboxEgressSettings (ADR-298) — the flag gate, the two lists, the one edit
 * (with or without the turn's data), the revoke, the stated cut and the
 * capacity gauge — and the two folds, CLOSED on arrival, the add form inside
 * the permissions fold. The i18n stub echoes keys, so controls are addressed
 * by key. `renderSection` opens every fold the section draws, as a reader
 * would before acting; `renderClosed` is the section as it arrives.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

/** The grants' own scope switches — the add form carries one more. */
const rowSwitches = () =>
  screen.getAllByRole('switch').filter(control => control.id.startsWith('egress-scope-'));

import type { EgressGrant, ReachableHost } from '@/types/sandbox-egress';

const setScope = vi.fn(async () => true);
const add = vi.fn(
  async (): Promise<{ ok: true; host: string } | { ok: false; code: string | null }> => ({
    ok: true,
    host: 'registry.npmjs.org',
  })
);
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
    add,
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

const renderClosed = () => render(<SandboxEgressSettings lng="fr" />);

/** The section with every fold it draws opened by a click on its summary. */
async function renderSection() {
  const view = renderClosed();
  const folds = Array.from(view.container.querySelectorAll('details'));
  for (const fold of folds) fireEvent.click(fold.querySelector('summary')!);
  await waitFor(() => {
    for (const fold of folds) expect(fold).toHaveAttribute('open');
  });
  return view;
}

describe('SandboxEgressSettings — gates', () => {
  it('renders nothing when the instance flag is off', () => {
    state.flagOn = false;
    const { container } = renderClosed();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the surface is unavailable', () => {
    state.unavailable = true;
    const { container } = renderClosed();
    expect(container).toBeEmptyDOMElement();
  });

  it('offers a retry on a transient failure, never a vanished section', () => {
    state.loadError = true;
    renderClosed();
    fireEvent.click(screen.getByRole('button', { name: /common\.retry/ }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe('SandboxEgressSettings — reachable without asking', () => {
  it('lists connector hosts with their brand name and operator hosts', async () => {
    await renderSection();
    expect(screen.getByText('api.search.brave.com')).toBeInTheDocument();
    expect(screen.getByText('api.example.org')).toBeInTheDocument();
    expect(screen.getByText('settings.sandbox_egress.source_connector')).toBeInTheDocument();
    expect(screen.getByText('settings.sandbox_egress.source_operator')).toBeInTheDocument();
  });

  it('says so when nothing is reachable', async () => {
    state.reachable = [];
    await renderSection();
    expect(screen.getByText('settings.sandbox_egress.reachable_empty')).toBeInTheDocument();
  });

  it('states when the instance refuses unknown hosts instead of asking', async () => {
    state.askEnabled = false;
    await renderSection();
    expect(screen.getByText('settings.sandbox_egress.ask_disabled')).toBeInTheDocument();
  });

  it('says nothing about refusal while the answer is in flight or asking is on', async () => {
    await renderSection();
    expect(screen.queryByText('settings.sandbox_egress.ask_disabled')).not.toBeInTheDocument();
  });
});

describe('SandboxEgressSettings — permissions', () => {
  it('draws each grant with its scope switch reflecting the stored decision', async () => {
    await renderSection();
    const switches = rowSwitches();
    expect(switches).toHaveLength(2);
    expect(switches[0]).toHaveAttribute('aria-checked', 'true');
    expect(switches[1]).toHaveAttribute('aria-checked', 'false');
  });

  it('changes the scope through the hook', async () => {
    await renderSection();
    fireEvent.click(rowSwitches()[0]);
    await waitFor(() => expect(setScope).toHaveBeenCalledWith('g-1', false));
  });

  it('revokes a grant through the hook, from a row menu named with its host', async () => {
    await renderSection();
    expect(
      screen.getAllByRole('button', { name: 'settings.sandbox_egress.row_menu' })
    ).toHaveLength(2);
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.sandbox_egress.revoke' })[1]);
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('g-2'));
  });

  it('shows the empty state when nothing was granted yet', async () => {
    state.grants = [];
    state.total = 0;
    await renderSection();
    expect(screen.getByText('settings.sandbox_egress.grants_empty')).toBeInTheDocument();
  });

  it('draws no permissions block where the instance never asks and none is held', async () => {
    state.askEnabled = false;
    state.grants = [];
    state.total = 0;
    await renderSection();
    expect(screen.queryByText('settings.sandbox_egress.grants_title')).not.toBeInTheDocument();
    expect(screen.queryByText('settings.sandbox_egress.grants_empty')).not.toBeInTheDocument();
  });

  it('keeps the permissions held before the instance stopped asking, revocable', async () => {
    state.askEnabled = false;
    await renderSection();
    expect(screen.getByText('settings.sandbox_egress.grants_title')).toBeInTheDocument();
    expect(
      screen.getAllByRole('button', { name: 'settings.sandbox_egress.row_menu' })
    ).toHaveLength(2);
  });

  it('states the cut when the exact total exceeds the page', async () => {
    state.total = 5;
    await renderSection();
    expect(screen.getByText('settings.sandbox_egress.grants_not_shown')).toBeInTheDocument();
  });

  it('draws the capacity against the published cap', async () => {
    await renderSection();
    const gauge = screen.getByRole('progressbar');
    expect(gauge).toHaveAttribute('aria-valuenow', '2');
    expect(gauge).toHaveAttribute('aria-valuemax', '50');
  });
});

describe('SandboxEgressSettings — allowing a host (ADR-327 lot 3)', () => {
  const field = () => screen.getByRole('textbox', { name: 'settings.sandbox_egress.add_label' });
  const submit = () => screen.getByRole('button', { name: 'settings.sandbox_egress.add_submit' });
  const scope = () => screen.getByRole('switch', { name: 'settings.sandbox_egress.add_scope' });

  it('offers no form where the instance never asks', async () => {
    state.askEnabled = false;
    await renderSection();
    expect(
      screen.queryByRole('textbox', { name: 'settings.sandbox_egress.add_label' })
    ).not.toBeInTheDocument();
  });

  it('offers no form while the instance has not said whether it asks', async () => {
    state.askEnabled = null;
    await renderSection();
    expect(
      screen.queryByRole('textbox', { name: 'settings.sandbox_egress.add_label' })
    ).not.toBeInTheDocument();
  });

  it('offers a field typed for a hostname, with no autocorrection', async () => {
    await renderSection();
    expect(field()).toHaveAttribute('autocapitalize', 'none');
    expect(field()).toHaveAttribute('spellcheck', 'false');
    expect(field()).toHaveAttribute('inputmode', 'url');
  });

  it("keeps the turn's data out unless the person switches it on", async () => {
    await renderSection();
    fireEvent.change(field(), { target: { value: ' registry.npmjs.org ' } });
    fireEvent.click(submit());
    await waitFor(() => expect(add).toHaveBeenCalledWith('registry.npmjs.org', false));
  });

  it('sends the scope the person chose and clears the field once allowed', async () => {
    await renderSection();
    fireEvent.change(field(), { target: { value: 'pypi.org' } });
    fireEvent.click(scope());
    fireEvent.click(submit());
    await waitFor(() => expect(add).toHaveBeenCalledWith('pypi.org', true));
    await waitFor(() => expect(field()).toHaveValue(''));
  });

  it('sends nothing for an empty field', async () => {
    await renderSection();
    expect(submit()).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(submit());
    expect(add).not.toHaveBeenCalled();
  });

  it('names the refusal beside the field and keeps what was typed', async () => {
    add.mockResolvedValueOnce({ ok: false, code: 'egress_grant_host_invalid' });
    await renderSection();
    fireEvent.change(field(), { target: { value: 'https://pypi.org' } });
    fireEvent.click(submit());
    const message = await screen.findByText(
      'settings.sandbox_egress.add_errors.egress_grant_host_invalid'
    );
    expect(field()).toHaveAttribute('aria-invalid', 'true');
    expect(field().getAttribute('aria-describedby')).toContain(message.id);
    expect(field()).toHaveValue('https://pypi.org');
  });

  it('falls back to the generic sentence for a refusal it cannot name', async () => {
    add.mockResolvedValueOnce({ ok: false, code: null });
    await renderSection();
    fireEvent.change(field(), { target: { value: 'pypi.org' } });
    fireEvent.click(submit());
    expect(await screen.findByText('common.error')).toBeInTheDocument();
  });
});

describe('SandboxEgressSettings — two folds, closed on arrival', () => {
  const summaryOf = (title: string) => screen.getByText(title).closest('summary')!;

  it('draws both lists folded, each with its description and exact count', () => {
    state.total = 7;
    renderClosed();
    const reachable = summaryOf('settings.sandbox_egress.reachable_title');
    const grants = summaryOf('settings.sandbox_egress.grants_title');
    expect(reachable.closest('details')).not.toHaveAttribute('open');
    expect(grants.closest('details')).not.toHaveAttribute('open');
    // Folded, the index says what each block holds and how much.
    expect(reachable).toHaveTextContent('settings.sandbox_egress.reachable_description');
    expect(reachable).toHaveTextContent('2');
    expect(grants).toHaveTextContent('settings.sandbox_egress.grants_description');
    expect(grants).toHaveTextContent('7');
    // Closed means unmounted: no host, no row, no form.
    expect(screen.queryByText('api.search.brave.com')).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('textbox', { name: 'settings.sandbox_egress.add_label' })
    ).not.toBeInTheDocument();
  });

  it('keeps the refusal to ask visible above the folds', () => {
    state.askEnabled = false;
    renderClosed();
    expect(screen.getByText('settings.sandbox_egress.ask_disabled')).toBeInTheDocument();
  });

  it('opens the reachable hosts alone on a click', async () => {
    renderClosed();
    fireEvent.click(summaryOf('settings.sandbox_egress.reachable_title'));
    expect(await screen.findByText('api.search.brave.com')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('holds the add form inside the permissions fold', async () => {
    renderClosed();
    fireEvent.click(summaryOf('settings.sandbox_egress.grants_title'));
    const field = await screen.findByRole('textbox', {
      name: 'settings.sandbox_egress.add_label',
    });
    expect(summaryOf('settings.sandbox_egress.grants_title').closest('details')).toContainElement(
      field
    );
    expect(screen.queryByText('api.search.brave.com')).not.toBeInTheDocument();
  });
});

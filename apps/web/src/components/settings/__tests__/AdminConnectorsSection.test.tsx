/**
 * AdminConnectorsSection — the global connector availability board: loading,
 * the "no config means enabled" default, the disabled badge + reason, the
 * disable flow behind its reason prompt (including cancellation), the enable
 * flow, the failure toast, and both branches of the optimistic cache updater
 * (patch an existing config vs append a missing one).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import {
  queryResult,
  mutationResult,
  mutateSpy,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';
import type { ConnectorConfig } from '../AdminConnectorsSection';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import AdminConnectorsSection from '../AdminConnectorsSection';

const ENDPOINT = '/connectors/admin/global-config';
const DISABLE = 'settings.admin.connectors.actions.disable';
const ENABLE = 'settings.admin.connectors.actions.enable';

function config(over: Partial<ConnectorConfig> = {}): ConnectorConfig {
  return {
    id: 'cfg-1',
    connector_type: 'google_gmail',
    is_enabled: true,
    disabled_reason: null,
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

let setData: ReturnType<typeof setDataSpy<ConnectorConfig[]>>;
let updateConfig: ReturnType<typeof mutateSpy>;

function stub(configs: ConnectorConfig[], loading = false) {
  setData = setDataSpy<ConnectorConfig[]>();
  useApiQuery.mockReturnValue(queryResult<ConnectorConfig[]>({ data: configs, loading, setData }));
}

/** The optimistic updater handed to setData, applied to a known previous state. */
function applyOptimistic(prev: ConnectorConfig[]): ConnectorConfig[] {
  const next = takeUpdater(setData)(prev);
  if (!next) throw new Error('the optimistic updater returned no list');
  return next;
}

beforeEach(() => {
  vi.clearAllMocks();
  updateConfig = mutateSpy().mockResolvedValue({});
  useApiMutation.mockReturnValue(mutationResult({ mutate: updateConfig }));
  stub([]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminConnectorsSection — rendering', () => {
  it('shows the loading placeholder while the config loads', () => {
    stub([], true);
    renderWithProviders(<AdminConnectorsSection lng="en" />);
    expect(screen.getByText('settings.admin.connectors.loading')).toBeInTheDocument();
  });

  it('treats a connector without config as enabled', () => {
    renderWithProviders(<AdminConnectorsSection lng="en" />);
    // Every connector defaults to enabled, so only "disable" affordances exist.
    expect(screen.getAllByRole('button', { name: DISABLE }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: ENABLE })).not.toBeInTheDocument();
  });

  it('surfaces a disabled connector with its reason', () => {
    stub([config({ is_enabled: false, disabled_reason: 'quota exceeded' })]);
    renderWithProviders(<AdminConnectorsSection lng="en" />);
    // Exactly one connector is disabled → a single enable affordance.
    expect(screen.getByRole('button', { name: ENABLE })).toBeInTheDocument();
    expect(screen.getByText(/quota exceeded/)).toBeInTheDocument();
  });
});

describe('AdminConnectorsSection — toggling', () => {
  it('does not disable when the reason prompt is dismissed', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null);
    const { user } = renderWithProviders(<AdminConnectorsSection lng="en" />);
    await user.click(screen.getAllByRole('button', { name: DISABLE })[0]);
    expect(updateConfig).not.toHaveBeenCalled();
    expect(setData).not.toHaveBeenCalled();
  });

  it('disables a connector with the captured reason and appends the missing config', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('abuse');
    const { user } = renderWithProviders(<AdminConnectorsSection lng="en" />);
    // The first category's first connector is google_gmail.
    await user.click(screen.getAllByRole('button', { name: DISABLE })[0]);
    await waitFor(() =>
      expect(updateConfig).toHaveBeenCalledWith(`${ENDPOINT}/google_gmail`, {
        is_enabled: false,
        disabled_reason: 'abuse',
      })
    );
    // Optimistic branch #1: no existing row → the updater appends one.
    const next = applyOptimistic([]);
    expect(next).toEqual([
      expect.objectContaining({
        connector_type: 'google_gmail',
        is_enabled: false,
        disabled_reason: 'abuse',
      }),
    ]);
  });

  it('re-enables a disabled connector without prompting and patches the existing config', async () => {
    const promptSpy = vi.spyOn(window, 'prompt');
    const existing = config({ is_enabled: false, disabled_reason: 'quota exceeded' });
    stub([existing]);
    const { user } = renderWithProviders(<AdminConnectorsSection lng="en" />);
    await user.click(screen.getByRole('button', { name: ENABLE }));
    await waitFor(() =>
      expect(updateConfig).toHaveBeenCalledWith(`${ENDPOINT}/google_gmail`, {
        is_enabled: true,
        disabled_reason: null,
      })
    );
    expect(promptSpy).not.toHaveBeenCalled();
    // Optimistic branch #2: the existing row is patched in place, not duplicated.
    const next = applyOptimistic([existing]);
    expect(next).toHaveLength(1);
    expect(next[0]).toMatchObject({ is_enabled: true, disabled_reason: null });
  });

  it('reports a failed toggle and leaves the cache untouched', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('abuse');
    updateConfig.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(<AdminConnectorsSection lng="en" />);
    await user.click(screen.getAllByRole('button', { name: DISABLE })[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(setData).not.toHaveBeenCalled();
  });
});

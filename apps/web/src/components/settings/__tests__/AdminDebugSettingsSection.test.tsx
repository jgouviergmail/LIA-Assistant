/**
 * AdminDebugSettingsSection — the two independent switches (the admin's own
 * debug panel and end-user access): loading, the status/default surfaces, each
 * toggle's PUT + optimistic cache patch + direction-specific toast, and the
 * failure path. The two queries and the two mutations are routed apart so a
 * regression that wires one switch to the other endpoint fails here.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import {
  queryResult,
  mutationResult,
  mutateSpy,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';
import type {
  DebugPanelEnabledResponse,
  DebugPanelUserAccessResponse,
} from '../AdminDebugSettingsSection';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import AdminDebugSettingsSection from '../AdminDebugSettingsSection';

const PANEL_ENDPOINT = '/admin/system-settings/debug-panel';
const ACCESS_ENDPOINT = '/admin/system-settings/debug-panel-user-access';
const PANEL_SWITCH = 'settings.admin.debug.toggleLabel';
const ACCESS_SWITCH = 'settings.admin.debug.userAccessToggleLabel';

function panelData(over: Partial<DebugPanelEnabledResponse> = {}): DebugPanelEnabledResponse {
  return { enabled: false, updated_by: null, updated_at: null, is_default: true, ...over };
}

function accessData(
  over: Partial<DebugPanelUserAccessResponse> = {}
): DebugPanelUserAccessResponse {
  return { available: false, updated_by: null, updated_at: null, is_default: true, ...over };
}

let setPanel: ReturnType<typeof setDataSpy<DebugPanelEnabledResponse>>;
let setAccess: ReturnType<typeof setDataSpy<DebugPanelUserAccessResponse>>;
let mutatePanel: ReturnType<typeof mutateSpy>;
let mutateAccess: ReturnType<typeof mutateSpy>;

function stub(
  panel: DebugPanelEnabledResponse,
  access: DebugPanelUserAccessResponse,
  loading = false
) {
  setPanel = setDataSpy<DebugPanelEnabledResponse>();
  setAccess = setDataSpy<DebugPanelUserAccessResponse>();
  useApiQuery.mockImplementation((endpoint: string) =>
    endpoint === PANEL_ENDPOINT
      ? queryResult<DebugPanelEnabledResponse>({ data: panel, loading, setData: setPanel })
      : queryResult<DebugPanelUserAccessResponse>({ data: access, loading, setData: setAccess })
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mutatePanel = mutateSpy().mockResolvedValue({});
  mutateAccess = mutateSpy().mockResolvedValue({});
  // Both mutations are PUT; they are told apart by componentName.
  useApiMutation.mockImplementation((opts: { componentName: string }) =>
    opts.componentName.endsWith('userAccess')
      ? mutationResult({ mutate: mutateAccess })
      : mutationResult({ mutate: mutatePanel })
  );
  stub(panelData(), accessData());
});

describe('AdminDebugSettingsSection — surfaces', () => {
  it('shows a loading placeholder until both queries settle', () => {
    stub(panelData(), accessData(), true);
    renderWithProviders(<AdminDebugSettingsSection lng="en" />);
    expect(screen.getByText('common.loading')).toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: PANEL_SWITCH })).not.toBeInTheDocument();
  });

  it('reflects an enabled panel and flags a value still on its default', () => {
    stub(panelData({ enabled: true, is_default: true }), accessData());
    renderWithProviders(<AdminDebugSettingsSection lng="en" />);
    expect(screen.getByRole('switch', { name: PANEL_SWITCH })).toBeChecked();
    expect(screen.getByText('settings.admin.debug.statusEnabled')).toBeInTheDocument();
    expect(screen.getByText('settings.admin.debug.usingDefault')).toBeInTheDocument();
  });

  it('keeps the two switches independent', () => {
    stub(panelData({ enabled: true, is_default: false }), accessData({ available: false }));
    renderWithProviders(<AdminDebugSettingsSection lng="en" />);
    expect(screen.getByRole('switch', { name: PANEL_SWITCH })).toBeChecked();
    expect(screen.getByRole('switch', { name: ACCESS_SWITCH })).not.toBeChecked();
  });
});

describe('AdminDebugSettingsSection — debug panel switch', () => {
  it('enables the panel, patches the cache optimistically and confirms', async () => {
    const { user } = renderWithProviders(
      <AdminDebugSettingsSection lng="en" />
    );
    await user.click(screen.getByRole('switch', { name: PANEL_SWITCH }));
    await waitFor(() =>
      expect(mutatePanel).toHaveBeenCalledWith(PANEL_ENDPOINT, { enabled: true })
    );
    expect(mutateAccess).not.toHaveBeenCalled();
    expect(takeUpdater(setPanel)(panelData())).toMatchObject({
      enabled: true,
      is_default: false,
    });
    expect(toast.success).toHaveBeenCalledWith('settings.admin.debug.enabledSuccess');
  });

  it('uses the disable wording when switching the panel off', async () => {
    stub(panelData({ enabled: true, is_default: false }), accessData());
    const { user } = renderWithProviders(
      <AdminDebugSettingsSection lng="en" />
    );
    await user.click(screen.getByRole('switch', { name: PANEL_SWITCH }));
    await waitFor(() =>
      expect(mutatePanel).toHaveBeenCalledWith(PANEL_ENDPOINT, { enabled: false })
    );
    expect(toast.success).toHaveBeenCalledWith('settings.admin.debug.disabledSuccess');
  });

  it('reports a failed panel update without touching the cache', async () => {
    mutatePanel.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(
      <AdminDebugSettingsSection lng="en" />
    );
    await user.click(screen.getByRole('switch', { name: PANEL_SWITCH }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('settings.admin.debug.error'));
    expect(setPanel).not.toHaveBeenCalled();
  });
});

describe('AdminDebugSettingsSection — user access switch', () => {
  it('opens access to end users through its own endpoint', async () => {
    const { user } = renderWithProviders(
      <AdminDebugSettingsSection lng="en" />
    );
    await user.click(screen.getByRole('switch', { name: ACCESS_SWITCH }));
    await waitFor(() =>
      expect(mutateAccess).toHaveBeenCalledWith(ACCESS_ENDPOINT, { available: true })
    );
    expect(mutatePanel).not.toHaveBeenCalled();
    expect(takeUpdater(setAccess)(accessData())).toMatchObject({
      available: true,
      is_default: false,
    });
    expect(toast.success).toHaveBeenCalledWith('settings.admin.debug.userAccessEnabledSuccess');
  });

  it('reports a failed access update', async () => {
    mutateAccess.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(
      <AdminDebugSettingsSection lng="en" />
    );
    await user.click(screen.getByRole('switch', { name: ACCESS_SWITCH }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('settings.admin.debug.error'));
    expect(setAccess).not.toHaveBeenCalled();
  });
});

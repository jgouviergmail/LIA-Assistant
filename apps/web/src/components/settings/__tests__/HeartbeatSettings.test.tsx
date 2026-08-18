/**
 * HeartbeatSettings — toggling the heartbeat (persist + result-driven toast).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useHeartbeatSettings } = vi.hoisted(() => ({ useHeartbeatSettings: vi.fn() }));
vi.mock('@/hooks/useHeartbeatSettings', () => ({ useHeartbeatSettings }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

// Kept although the weather-location block moved to the Google Places
// connector (2026-08-16): child blocks inside the enabled panel may read the
// auth context, and the stub keeps the panel mountable in isolation.
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: null, isLoading: false }) }));

// The history hook is spied rather than stubbed away: whether it is called
// with `enabled: false` while the block is shut is the property under test,
// not an implementation detail.
const { useHeartbeatHistory } = vi.hoisted(() => ({
  useHeartbeatHistory: vi.fn(() => ({
    notifications: undefined,
    total: 0,
    firstLoad: false,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
}));
vi.mock('@/hooks/useHeartbeatHistory', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useHeartbeatHistory')>();
  return { ...actual, useHeartbeatHistory };
});

import { HeartbeatSettings } from '../HeartbeatSettings';
import type { useHeartbeatSettings as useHeartbeatSettingsFn } from '@/hooks/useHeartbeatSettings';

type HeartbeatHook = ReturnType<typeof useHeartbeatSettingsFn>;

function hook(over: Partial<HeartbeatHook> = {}) {
  return {
    // Mirrors `HeartbeatSettings` exactly. The previous fixture invented
    // `heartbeat_frequency_min` / `heartbeat_active_hours_start`, which the
    // API has never returned — a mock that drifts from the contract keeps the
    // suite green over a component reading `undefined`.
    settings: {
      heartbeat_enabled: false,
      heartbeat_min_per_day: 2,
      heartbeat_max_per_day: 6,
      heartbeat_push_enabled: false,
      heartbeat_notify_start_hour: 8,
      heartbeat_notify_end_hour: 22,
      available_sources: ['calendar'],
      disabled_sources: [],
      all_sources: ['calendar', 'emails'],
    },
    loading: false,
    updating: false,
    updateSettings: vi.fn().mockResolvedValue({ ok: true }),
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('HeartbeatSettings', () => {
  it('enabling the heartbeat persists it and toasts success', async () => {
    const updateSettings = vi.fn().mockResolvedValue({ ok: true });
    useHeartbeatSettings.mockReturnValue(hook({ updateSettings }));
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" />);
    await user.click(screen.getAllByRole('switch')[0]);
    expect(updateSettings).toHaveBeenCalledWith({ heartbeat_enabled: true });
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('toasts an error when the update returns a falsy result', async () => {
    const updateSettings = vi.fn().mockResolvedValue(null);
    useHeartbeatSettings.mockReturnValue(hook({ updateSettings }));
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" />);
    await user.click(screen.getAllByRole('switch')[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});

describe('HeartbeatSettings — per-source permission (ADR-197)', () => {
  it('renders one switch per source the SERVER publishes, not a hardcoded list', async () => {
    // The panel used to hard-code seven names while the backend computed
    // eight: `health_signals` was never shown at all. The vocabulary now
    // travels in `all_sources`.
    useHeartbeatSettings.mockReturnValue(
      hook({
        settings: {
          ...hook().settings,
          heartbeat_enabled: true,
          all_sources: ['calendar', 'health_signals', 'departure'],
          available_sources: ['calendar'],
          disabled_sources: [],
        },
      })
    );
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" />);

    // The switches live behind a disclosure that is CLOSED on arrival.
    await user.click(await screen.findByText('heartbeat.sources_permission_title'));

    expect(
      await screen.findByRole('switch', { name: 'heartbeat.source_health_signals' })
    ).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'heartbeat.source_departure' })).toBeInTheDocument();
  });

  it('carries the published dependency through to the switch', async () => {
    // The server declaring the constraint is worth nothing if the section
    // drops it on the way to the panel — this is the wire, not the rule.
    useHeartbeatSettings.mockReturnValue(
      hook({
        settings: {
          ...hook().settings,
          heartbeat_enabled: true,
          all_sources: ['calendar', 'departure'],
          available_sources: ['calendar', 'departure'],
          disabled_sources: ['calendar'],
          source_dependencies: { departure: ['calendar'] },
        },
      })
    );
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" />);
    await user.click(await screen.findByText('heartbeat.sources_permission_title'));

    expect(await screen.findByText('heartbeat.source_requires')).toBeInTheDocument();
  });

  it('persists the full refusal set when a source is switched off', async () => {
    const updateSettings = vi.fn().mockResolvedValue({ ok: true });
    useHeartbeatSettings.mockReturnValue(
      hook({
        updateSettings,
        settings: {
          ...hook().settings,
          heartbeat_enabled: true,
          all_sources: ['calendar', 'emails'],
          disabled_sources: ['calendar'],
        },
      })
    );
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" />);
    await user.click(await screen.findByText('heartbeat.sources_permission_title'));

    await user.click(await screen.findByRole('switch', { name: 'heartbeat.source_emails' }));

    expect(updateSettings).toHaveBeenCalledWith({
      heartbeat_disabled_sources: ['calendar', 'emails'],
    });
  });
});

describe('HeartbeatSettings — folded by default', () => {
  // The panel stacks a frequency form, eleven source switches and a ten-row
  // history. Shown at once that is a wall, and the reader came to change one
  // thing. Both blocks fold CLOSED; the history additionally does not FETCH
  // until opened, which is the difference between "not shown" and "not paid
  // for".
  function enabledPanel() {
    useHeartbeatSettings.mockReturnValue(
      hook({
        settings: {
          ...hook().settings,
          heartbeat_enabled: true,
          all_sources: ['calendar', 'emails'],
          available_sources: ['calendar'],
          disabled_sources: ['emails'],
        },
      })
    );
  }

  it('hides the eleven switches until the reader asks for them', async () => {
    enabledPanel();
    renderWithProviders(<HeartbeatSettings lng="en" />);

    expect(await screen.findByText('heartbeat.sources_permission_title')).toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: 'heartbeat.source_calendar' })).toBeNull();
  });

  it('still says how many sources are refused while folded', async () => {
    // Folded, the badge is the only thing left to judge from — silencing a
    // source must not become invisible just because the block is shut.
    enabledPanel();
    renderWithProviders(<HeartbeatSettings lng="en" />);

    await screen.findByText('heartbeat.sources_permission_title');
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('does not fetch the history until its block is opened', async () => {
    enabledPanel();
    renderWithProviders(<HeartbeatSettings lng="en" />);

    await screen.findByText('heartbeat.history.title');
    // `enabled: false` while shut: a collapsed list must not cost a request.
    expect(useHeartbeatHistory).toHaveBeenCalledWith(false);
  });

  it('fetches it once the reader opens it', async () => {
    enabledPanel();
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" />);

    await user.click(await screen.findByText('heartbeat.history.title'));

    expect(useHeartbeatHistory).toHaveBeenLastCalledWith(true);
  });
});

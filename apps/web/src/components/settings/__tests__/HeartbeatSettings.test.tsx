/**
 * HeartbeatSettings — toggling the heartbeat (persist + result-driven toast).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useHeartbeatSettings } = vi.hoisted(() => ({ useHeartbeatSettings: vi.fn() }));
vi.mock('@/hooks/useHeartbeatSettings', () => ({ useHeartbeatSettings }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { HeartbeatSettings } from '../HeartbeatSettings';
import type { useHeartbeatSettings as useHeartbeatSettingsFn } from '@/hooks/useHeartbeatSettings';

type HeartbeatHook = ReturnType<typeof useHeartbeatSettingsFn>;

function hook(over: Partial<HeartbeatHook> = {}) {
  return {
    settings: {
      heartbeat_enabled: false,
      heartbeat_push_enabled: false,
      heartbeat_frequency_min: 2,
      heartbeat_frequency_max: 6,
      heartbeat_active_hours_start: 8,
      heartbeat_active_hours_end: 22,
    },
    loading: false,
    updating: false,
    updateSettings: vi.fn().mockResolvedValue({ ok: true }),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('HeartbeatSettings', () => {
  it('enabling the heartbeat persists it and toasts success', async () => {
    const updateSettings = vi.fn().mockResolvedValue({ ok: true });
    useHeartbeatSettings.mockReturnValue(hook({ updateSettings }));
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" collapsible={false} />);
    await user.click(screen.getAllByRole('switch')[0]);
    expect(updateSettings).toHaveBeenCalledWith({ heartbeat_enabled: true });
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('toasts an error when the update returns a falsy result', async () => {
    const updateSettings = vi.fn().mockResolvedValue(null);
    useHeartbeatSettings.mockReturnValue(hook({ updateSettings }));
    const { user } = renderWithProviders(<HeartbeatSettings lng="en" collapsible={false} />);
    await user.click(screen.getAllByRole('switch')[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});

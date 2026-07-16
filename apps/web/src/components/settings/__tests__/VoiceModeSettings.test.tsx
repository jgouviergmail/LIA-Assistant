/**
 * VoiceModeSettings — the enable/disable switch (persist + store sync + refresh
 * + toast) and the STT backend picker (local/remote), including the guard when
 * the remote backend is unavailable.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { storeEnable, storeDisable } = vi.hoisted(() => ({
  storeEnable: vi.fn(),
  storeDisable: vi.fn(),
}));
vi.mock('@/stores/voiceModeStore', () => ({
  useVoiceModeStore: () => ({ enable: storeEnable, disable: storeDisable }),
}));
const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { VoiceModeSettings } from '../VoiceModeSettings';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ stt_remote_available: true });
  patch.mockResolvedValue({});
});

describe('VoiceModeSettings — enable switch', () => {
  it('enabling persists, syncs the store, refreshes and toasts', async () => {
    const ctx = authed({ voice_mode_enabled: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<VoiceModeSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-mode-preference', {
        voice_mode_enabled: true,
      })
    );
    expect(storeEnable).toHaveBeenCalled();
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });
});

describe('VoiceModeSettings — STT picker', () => {
  it('switching to the remote backend persists the new mode', async () => {
    useAuth.mockReturnValue(authed({ voice_stt_mode: 'local' }));
    const { user } = renderWithProviders(<VoiceModeSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: /stt_mode_remote/ }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-mode-preference', {
        voice_stt_mode: 'remote',
      })
    );
  });

  it('does not persist when re-selecting the already-active backend', async () => {
    useAuth.mockReturnValue(authed({ voice_stt_mode: 'local' }));
    const { user } = renderWithProviders(<VoiceModeSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: /stt_mode_local/ }));
    expect(patch).not.toHaveBeenCalled();
  });

  it('warns and does not persist when the remote backend is unavailable', async () => {
    get.mockResolvedValue({ stt_remote_available: false });
    useAuth.mockReturnValue(authed({ voice_stt_mode: 'local' }));
    renderWithProviders(<VoiceModeSettings lng="en" collapsible={false} />);
    // Wait for the mount probe to mark the remote backend unavailable.
    await waitFor(() =>
      expect(
        screen.getByText('settings.voice_mode.stt_remote_unavailable_warning')
      ).toBeInTheDocument()
    );
    // The remote option is disabled; the guard also blocks the handler.
    expect(screen.getByRole('button', { name: /stt_mode_remote/ })).toBeDisabled();
    expect(patch).not.toHaveBeenCalled();
  });
});

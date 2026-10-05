/**
 * VoiceModeSettings — the enable/disable switch (persist + store sync + refresh
 * + toast) and the STT backend picker (local/remote), including the guard when
 * the remote backend is unavailable.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
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
  useAuth.mockReturnValue(authed());
});

describe('VoiceModeSettings — enable switch', () => {
  it('enabling persists, syncs the store, refreshes and toasts', async () => {
    const ctx = authed({ voice_mode_enabled: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<VoiceModeSettings lng="en" />);
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
    const { user } = renderWithProviders(<VoiceModeSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: /stt_mode_remote/ }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-mode-preference', {
        voice_stt_mode: 'remote',
      })
    );
  });

  it('does not persist when re-selecting the already-active backend', async () => {
    useAuth.mockReturnValue(authed({ voice_stt_mode: 'local' }));
    const { user } = renderWithProviders(<VoiceModeSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: /stt_mode_local/ }));
    expect(patch).not.toHaveBeenCalled();
  });

  it('warns and does not persist when the remote backend is unavailable', async () => {
    get.mockResolvedValue({ stt_remote_available: false });
    useAuth.mockReturnValue(authed({ voice_stt_mode: 'local' }));
    renderWithProviders(<VoiceModeSettings lng="en" />);
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

  it("says how to cut LIA's voice by voice, and that the wake word is in beta", async () => {
    await act(async () => {
      renderWithProviders(<VoiceModeSettings lng="fr" />);
    });
    expect(screen.getByText('settings.voice_mode.stop_note')).toBeInTheDocument();
    expect(screen.getByText('settings.voice_mode.enable_description')).toBeInTheDocument();
    expect(screen.getByText('settings.voice_mode.wake_beta')).toBeInTheDocument();
    expect(screen.getByText('settings.voice_mode.wake_beta_note')).toBeInTheDocument();
  });

  it('never names a phrase in a language no model ships for', async () => {
    await act(async () => {
      renderWithProviders(<VoiceModeSettings lng="de" />);
    });
    expect(screen.getByText('settings.voice_mode.enable_description_no_model')).toBeInTheDocument();
    expect(screen.queryByText('settings.voice_mode.enable_description')).toBeNull();
    expect(screen.queryByText('settings.voice_mode.stop_note')).toBeNull();
    expect(screen.queryByText('settings.voice_mode.wake_beta')).toBeNull();
  });
});

describe('VoiceModeSettings — titled sub-blocks', () => {
  it('names the engine picker and the hands-free switch by their titles, each with a theme icon', async () => {
    useAuth.mockReturnValue(authed());
    await act(async () => {
      renderWithProviders(<VoiceModeSettings lng="en" />);
    });
    const engine = screen.getByRole('group', { name: 'settings.voice_mode.stt_mode_label' });
    expect(engine).toContainElement(screen.getByRole('button', { name: /stt_mode_local/ }));
    expect(screen.getByRole('switch', { name: 'settings.voice_mode.enable' })).toBeInTheDocument();
    for (const title of ['settings.voice_mode.stt_mode_label', 'settings.voice_mode.enable']) {
      const heading = screen.getByText(title).closest('p');
      const icon = heading?.querySelector('svg');
      expect(icon).toHaveAttribute('aria-hidden', 'true');
      expect(icon).toHaveClass('text-primary');
    }
  });
});

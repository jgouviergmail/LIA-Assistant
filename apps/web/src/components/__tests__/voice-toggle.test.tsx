/**
 * VoiceToggle — the enable/disable affordance, the optimistic PATCH + audio
 * warmup + refresh + toast on success, the error toast, and the no-user guard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
const { warmupAudio } = vi.hoisted(() => ({ warmupAudio: vi.fn() }));
vi.mock('@/hooks/useVoicePlayback', () => ({ useVoicePlayback: () => ({ warmupAudio }) }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { VoiceToggle } from '../voice-toggle';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  warmupAudio.mockResolvedValue(undefined);
});

describe('VoiceToggle', () => {
  it('offers to enable voice when it is off', () => {
    useAuth.mockReturnValue(authed({ voice_enabled: false }));
    renderWithProviders(<VoiceToggle />);
    expect(screen.getByRole('button', { name: 'voice.toggle.enable' })).toBeInTheDocument();
  });

  it('enabling voice persists, warms up audio, refreshes and toasts', async () => {
    const ctx = authed({ voice_enabled: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-preference', { voice_enabled: true })
    );
    expect(warmupAudio).toHaveBeenCalled();
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('does not warm up audio when disabling voice', async () => {
    useAuth.mockReturnValue(authed({ voice_enabled: true }));
    const { user } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-preference', { voice_enabled: false })
    );
    expect(warmupAudio).not.toHaveBeenCalled();
  });

  it('shows an error toast when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('is disabled when no user is authenticated', () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    renderWithProviders(<VoiceToggle />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});

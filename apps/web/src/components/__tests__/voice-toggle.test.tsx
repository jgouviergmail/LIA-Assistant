/**
 * VoiceToggle — the enable/disable affordance, the optimistic PATCH + audio
 * warmup + refresh + toast on success, the error toast, and the no-user guard.
 * With the live mode offered (ADR-299, wave 2 A1): a menu with the spoken
 * replies and « open a live session », which asks the store and navigates to
 * the chat page when the person is elsewhere.
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
const live = vi.hoisted(() => ({
  available: false,
  directTools: false,
  pathname: '/fr/dashboard',
  push: vi.fn(),
}));
vi.mock('@/hooks/useLiveAvailability', () => ({
  useLiveAvailability: () => ({
    available: live.available,
    provider: live.available ? 'gemini' : null,
    directTools: live.available && live.directTools,
  }),
}));
// The stubbed `t` returns its key alone; here the options are needed to
// see the provider's brand reach the live entry.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));
vi.mock('next/navigation', () => ({ usePathname: () => live.pathname }));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push: live.push }),
}));

import { useLiveStore } from '@/stores/liveStore';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';

import { VoiceToggle } from '../voice-toggle';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  warmupAudio.mockResolvedValue(undefined);
  live.available = false;
  live.pathname = '/fr/dashboard';
  useLiveStore.getState().reset();
  useMeetingRecorderStore.getState().reset();
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

describe('VoiceToggle with the live mode offered', () => {
  beforeEach(() => {
    live.available = true;
  });

  it('is a menu: the spoken replies as a checkbox, the live session as an entry', async () => {
    useAuth.mockReturnValue(authed({ voice_enabled: true }));
    const { user } = renderWithProviders(<VoiceToggle />);
    const trigger = screen.getByRole('button', { name: 'voice.toggle.menu' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    await user.click(trigger);
    const comments = await screen.findByRole('menuitemcheckbox', { name: 'voice.toggle.comments' });
    expect(comments).toHaveAttribute('aria-checked', 'true');
    // The live entry is named after the provider's BRAND (owner decision
    // 2026-09-19), drawn like its neighbour, an icon before each.
    const entry = screen.getByRole('menuitem', { name: /voice\.toggle\.live_start/ });
    expect(entry).toHaveTextContent('{"provider":"Gemini"}');
    expect(entry).not.toHaveClass('text-primary');
    expect(entry.querySelector('svg')).not.toBeNull();
    expect(comments.querySelector('svg.lucide-volume-2')).not.toBeNull();
    await user.click(comments);
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-preference', { voice_enabled: false })
    );
  });

  it('asks the store for a start and navigates to the chat page from elsewhere', async () => {
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    await user.click(await screen.findByRole('menuitem', { name: /voice\.toggle\.live_start/ }));
    expect(useLiveStore.getState().pendingStart).toBe('delegated');
    expect(live.push).toHaveBeenCalledWith('/dashboard/chat');
  });

  it('offers a DIRECT session as a third entry only where the model can hold one', async () => {
    // ADR-300 wave 4: after the spoken replies and the live session, « Direct
    // live session (<brand>) » — hidden on a wire that carries no tool schema.
    useAuth.mockReturnValue(authed());
    const { user, unmount } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    await screen.findByRole('menuitem', { name: /voice\.toggle\.live_start/ });
    expect(screen.queryByRole('menuitem', { name: /live_direct_start/ })).toBeNull();
    unmount();
    live.directTools = true;
    const second = renderWithProviders(<VoiceToggle />);
    await second.user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    const items = await screen.findAllByRole('menuitem');
    expect(items.map(item => item.textContent)).toEqual([
      expect.stringContaining('voice.toggle.live_start'),
      expect.stringContaining('voice.toggle.live_direct_start'),
    ]);
    expect(items[1]).toHaveTextContent('{"provider":"Gemini"}');
    await second.user.click(items[1]);
    expect(useLiveStore.getState().pendingStart).toBe('direct');
    expect(live.push).toHaveBeenCalledWith('/dashboard/chat');
    live.directTools = false;
  });

  it('does not navigate when already on the chat page', async () => {
    live.pathname = '/fr/dashboard/chat';
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    await user.click(await screen.findByRole('menuitem', { name: /voice\.toggle\.live_start/ }));
    expect(useLiveStore.getState().pendingStart).toBe('delegated');
    expect(live.push).not.toHaveBeenCalled();
  });

  it('switches the spoken replies off, without a word, when a live session is asked for', async () => {
    // Exclusive voices (owner decision 2026-09-19): the session takes the voice.
    useAuth.mockReturnValue(authed({ voice_enabled: true }));
    const { user } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    await user.click(await screen.findByRole('menuitem', { name: /voice\.toggle\.live_start/ }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/voice-preference', { voice_enabled: false })
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(useLiveStore.getState().pendingStart).toBe('delegated');
  });

  it('shows the live voice on the icon and refuses the spoken replies while a session is open', async () => {
    useAuth.mockReturnValue(authed({ voice_enabled: false }));
    useLiveStore.getState().begin('s');
    useLiveStore.getState().apply('minted');
    useLiveStore.getState().apply('setup_complete');
    const { user } = renderWithProviders(<VoiceToggle />);
    const trigger = screen.getByRole('button', { name: 'voice.toggle.menu' });
    // The waveform in the primary colour: the live session is the voice that is on.
    expect(trigger.querySelector('svg.lucide-audio-lines')).toHaveClass('text-primary');
    expect(trigger).toHaveAttribute('title', 'voice.toggle.live_active');
    await user.click(trigger);
    const comments = await screen.findByRole('menuitemcheckbox', {
      name: /voice\.toggle\.comments/,
    });
    expect(comments).toHaveAttribute('aria-disabled', 'true');
    expect(comments).toHaveTextContent('voice.toggle.comments_live_busy');
  });

  it('refuses a second session while one is open, and while a meeting records', async () => {
    useAuth.mockReturnValue(authed());
    useLiveStore.getState().begin('s');
    useLiveStore.getState().apply('minted');
    const { user, unmount } = renderWithProviders(<VoiceToggle />);
    await user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    const entry = await screen.findByRole('menuitem', { name: /voice\.toggle\.live_start/ });
    expect(entry).toHaveAttribute('aria-disabled', 'true');
    expect(entry).toHaveTextContent('voice.toggle.live_busy');
    unmount();
    useLiveStore.getState().reset();
    useMeetingRecorderStore.setState({ phase: 'recording' });
    const second = renderWithProviders(<VoiceToggle />);
    await second.user.click(screen.getByRole('button', { name: 'voice.toggle.menu' }));
    const blocked = await screen.findByRole('menuitem', { name: /voice\.toggle\.live_start/ });
    expect(blocked).toHaveAttribute('aria-disabled', 'true');
    expect(blocked).toHaveTextContent('voice.toggle.live_meeting');
  });
});

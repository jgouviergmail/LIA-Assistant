/**
 * VoiceModeBadge — always in the header: greyed while hands-free mode is off
 * (a tap turns it on), an icon alone in every state, the tap-to-speak /
 * tap-to-stop transitions per state, the disabled processing state, and the
 * long press — pointer or held Space — that turns it off (with its announcement +
 * server sync).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, fireEvent, act } from '@/__tests__/test-utils';
import type { useVoiceMode as useVoiceModeFn } from '@/hooks/useVoiceMode';

const { useVoiceMode } = vi.hoisted(() => ({ useVoiceMode: vi.fn() }));
vi.mock('@/hooks/useVoiceMode', () => ({ useVoiceMode }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({
  toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({ logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { VoiceModeBadge } from '../VoiceModeBadge';

type VMHook = ReturnType<typeof useVoiceModeFn>;

function vm(over: Partial<VMHook> = {}) {
  return {
    isEnabled: true,
    state: 'listening' as VMHook['state'],
    isRecording: false,
    isProcessing: false,
    isSpeaking: false,
    isListening: true,
    wakeWordState: 'listening' as VMHook['wakeWordState'],
    wakePhrase: 'Dis LIA',
    stopWord: null,
    enable: vi.fn(),
    disable: vi.fn(),
    startRecording: vi.fn().mockResolvedValue(undefined),
    stopRecording: vi.fn(),
    isSupported: true,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  useAuth.mockReturnValue({ refreshUser: vi.fn() });
  useVoiceMode.mockReturnValue(vm());
});

describe('VoiceModeBadge', () => {
  it('stays in the header while hands-free mode is off, named by what a tap does', () => {
    useVoiceMode.mockReturnValue(vm({ isEnabled: false, state: 'idle', isListening: false }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button', { name: 'chat.voice_mode.enable' });
    expect(badge).toBeEnabled();
    expect(badge).toHaveAttribute('aria-pressed', 'false');
    // Nothing to turn off yet, so the tooltip names the tap alone.
    expect(badge).toHaveAttribute('title', 'chat.voice_mode.enable');
  });

  it('a tap while off turns hands-free mode on and persists it', async () => {
    const enable = vi.fn();
    useVoiceMode.mockReturnValue(
      vm({ isEnabled: false, state: 'idle', isListening: false, enable })
    );
    const { user } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.enable' }));
    expect(enable).toHaveBeenCalledTimes(1);
    // Announced beside the badge, never toasted: a toast stacks over the badge
    // and would swallow the next click (the one that turns the mode back on).
    expect(screen.getByRole('status')).toHaveTextContent('settings.voice_mode.enabled_success');
    expect(toast.success).not.toHaveBeenCalled();
    expect(patch).toHaveBeenCalledWith('/auth/me/voice-mode-preference', {
      voice_mode_enabled: true,
    });
  });

  it('a long press while off never turns anything off — its release turns it on', () => {
    const enable = vi.fn();
    const disable = vi.fn();
    useVoiceMode.mockReturnValue(
      vm({ isEnabled: false, state: 'idle', isListening: false, enable, disable })
    );
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.mouseDown(badge);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      fireEvent.mouseUp(badge);
      fireEvent.click(badge);
    } finally {
      vi.useRealTimers();
    }
    expect(disable).not.toHaveBeenCalled();
    expect(enable).toHaveBeenCalledTimes(1);
  });

  it('shows an icon alone in every state — the words ride the accessible name', () => {
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button', { name: 'chat.voice_mode.hint_listening' });
    expect(badge.textContent).toBe('');
  });

  it('tells how to turn the mode off in its tooltip while it is on', () => {
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(screen.getByRole('button')).toHaveAttribute(
      'title',
      'chat.voice_mode.hint_listening\nchat.voice_mode.hold_to_disable'
    );
  });

  it('tells speaking from listening by its icon, now that no label does', () => {
    useVoiceMode.mockReturnValue(vm({ state: 'speaking', isSpeaking: true, isListening: false }));
    const { container, unmount } = renderWithProviders(
      <VoiceModeBadge onTranscription={vi.fn()} />
    );
    const speakingIcon = container.querySelector('svg')?.getAttribute('class');
    unmount();
    useVoiceMode.mockReturnValue(vm());
    const listening = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const listeningIcon = listening.container.querySelector('svg')?.getAttribute('class');
    expect(speakingIcon).toBeTruthy();
    expect(speakingIcon).not.toBe(listeningIcon);
  });

  it('starts recording on a tap while listening', async () => {
    const startRecording = vi.fn().mockResolvedValue(undefined);
    useVoiceMode.mockReturnValue(vm({ state: 'listening', startRecording }));
    const { user } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.hint_listening' }));
    expect(startRecording).toHaveBeenCalledTimes(1);
  });

  it('names the stop command beside the phrase when the model ships it', () => {
    useVoiceMode.mockReturnValue(vm({ stopWord: 'LIA, stop' }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(
      screen.getByRole('button', { name: 'chat.voice_mode.hint_listening_stop' })
    ).toBeInTheDocument();
  });

  it('stops recording on a tap while recording', async () => {
    const stopRecording = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'recording', isRecording: true, stopRecording }));
    const { user } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.click_to_stop' }));
    expect(stopRecording).toHaveBeenCalledTimes(1);
  });

  it('disables the badge while processing', () => {
    useVoiceMode.mockReturnValue(vm({ state: 'processing', isProcessing: true }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice_mode.processing' })).toBeDisabled();
  });

  it('turns hands-free mode off on a long press', () => {
    const disable = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.mouseDown(badge);
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(disable).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('settings.voice_mode.disabled_success');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('holding Space is the keyboard long press, and its release is no tap', () => {
    const disable = vi.fn();
    const startRecording = vi.fn().mockResolvedValue(undefined);
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable, startRecording }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.keyDown(badge, { key: ' ' });
      act(() => {
        vi.advanceTimersByTime(500);
      });
      fireEvent.keyUp(badge, { key: ' ' });
      // The browser activates a button on Space's release.
      fireEvent.click(badge);
    } finally {
      vi.useRealTimers();
    }
    expect(disable).toHaveBeenCalledTimes(1);
    expect(startRecording).not.toHaveBeenCalled();
  });

  it('a short Space press stays a tap', () => {
    const disable = vi.fn();
    const startRecording = vi.fn().mockResolvedValue(undefined);
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable, startRecording }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.keyDown(badge, { key: ' ' });
      act(() => {
        vi.advanceTimersByTime(200);
      });
      fireEvent.keyUp(badge, { key: ' ' });
      fireEvent.click(badge);
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(disable).not.toHaveBeenCalled();
    expect(startRecording).toHaveBeenCalledTimes(1);
  });

  it('a held Space abandoned by a blur never fires', () => {
    const disable = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.keyDown(badge, { key: ' ' });
      fireEvent.blur(badge);
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(disable).not.toHaveBeenCalled();
  });

  it('persists the preference server-side after a long press', async () => {
    useVoiceMode.mockReturnValue(vm({ state: 'listening' }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    vi.useFakeTimers();
    try {
      fireEvent.mouseDown(screen.getByRole('button'));
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(patch).toHaveBeenCalledWith('/auth/me/voice-mode-preference', {
      voice_mode_enabled: false,
    });
  });

  it('a press released before the threshold never toggles', () => {
    const disable = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.mouseDown(badge);
      act(() => {
        vi.advanceTimersByTime(200);
      });
      fireEvent.mouseUp(badge);
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(disable).not.toHaveBeenCalled();
  });

  it('cancels the long press when the pointer leaves the badge', () => {
    const disable = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.mouseDown(badge);
      fireEvent.mouseLeave(badge);
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(disable).not.toHaveBeenCalled();
  });

  it('a touch press is cancellable too and suppresses the native selection', () => {
    const disable = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', disable }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    const badge = screen.getByRole('button');
    vi.useFakeTimers();
    try {
      fireEvent.touchStart(badge, { touches: [{ clientX: 0, clientY: 0 }] });
      fireEvent.touchEnd(badge, { touches: [] });
      act(() => {
        vi.advanceTimersByTime(500);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(disable).not.toHaveBeenCalled();
  });

  it('hints to hold while speaking instead of interrupting', async () => {
    useVoiceMode.mockReturnValue(vm({ state: 'speaking', isSpeaking: true }));
    const { user } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.speaking' }));
    expect(toast.info).toHaveBeenCalledWith('chat.voice_mode.hold_to_disable');
  });

  it('shows the initializing state while the wake-word model loads', () => {
    useVoiceMode.mockReturnValue(vm({ wakeWordState: 'loading', wakePhrase: null }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice_mode.badge_initializing' })).toBeTruthy();
  });

  it.each(['unavailable', 'idle'] as const)(
    'offers tap-to-speak, never a permanent « initializing », when the wake word is %s',
    wakeWordState => {
      // No model for the language, no runtime, a refused or borrowed
      // microphone: voice still works tap-to-speak.
      useVoiceMode.mockReturnValue(vm({ wakeWordState, wakePhrase: null }));
      renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
      expect(screen.getByRole('button', { name: 'chat.voice_mode.click_to_speak' })).toBeTruthy();
    }
  );

  it.each([true, false])(
    'is disabled and says why when the browser cannot capture (mode on: %s)',
    isEnabled => {
      useVoiceMode.mockReturnValue(vm({ isSupported: false, isEnabled }));
      renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
      expect(
        screen.getByRole('button', { name: 'chat.voice_mode.error_not_supported' })
      ).toBeDisabled();
    }
  );

  it.each([true, false])('is disabled when the caller disables it (mode on: %s)', isEnabled => {
    useVoiceMode.mockReturnValue(vm({ isEnabled, state: isEnabled ? 'listening' : 'idle' }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} disabled />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});

/**
 * The error the USER is shown is chosen from the failure, not from a generic
 * catch-all: a denied microphone, an unsupported browser and a broken ticket
 * exchange each deserve their own remedy. The component owns that mapping and
 * hands it to `useVoiceMode` as `onError`.
 */
describe('VoiceModeBadge — error surfacing', () => {
  /** Invoke the `onError` the component registered on the hook. */
  function raise(error: Error): void {
    const options = useVoiceMode.mock.calls[0]?.[0] as { onError?: (e: Error) => void } | undefined;
    options?.onError?.(error);
  }

  it.each([
    ['permission denied by the browser', 'chat.voice_mode.error_permission'],
    ['Permission denied', 'chat.voice_mode.error_permission'],
    ['getUserMedia is not supported here', 'chat.voice_mode.error_not_supported'],
    ['ticket exchange failed', 'chat.voice_mode.error_connection'],
    ['Connection closed', 'chat.voice_mode.error_connection'],
    ['boom', 'chat.voice_mode.error_generic'],
  ])('%s → %s', (message, expected) => {
    useVoiceMode.mockReturnValue(vm());
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    raise(new Error(message));
    expect(toast.error).toHaveBeenCalledWith(expected);
  });
});

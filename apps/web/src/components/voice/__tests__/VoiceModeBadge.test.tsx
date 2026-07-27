/**
 * VoiceModeBadge — hidden while voice mode is off, the tap-to-speak /
 * tap-to-stop transitions per state, the disabled processing state, and the
 * long-press toggle (with its toast + server sync).
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
    isKwsListening: true,
    isKwsSupported: true,
    toggle: vi.fn(),
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
  it('renders nothing while voice mode is disabled', () => {
    useVoiceMode.mockReturnValue(vm({ isEnabled: false }));
    const { container } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('starts recording on a tap while listening', async () => {
    const startRecording = vi.fn().mockResolvedValue(undefined);
    useVoiceMode.mockReturnValue(vm({ state: 'listening', startRecording }));
    const { user } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.click_to_speak' }));
    expect(startRecording).toHaveBeenCalledTimes(1);
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

  it('toggles voice mode off on a long press', () => {
    const toggle = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', toggle }));
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
    expect(toggle).toHaveBeenCalledTimes(1);
    expect(toast.info).toHaveBeenCalledTimes(1);
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
    const toggle = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', toggle }));
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
    expect(toggle).not.toHaveBeenCalled();
  });

  it('cancels the long press when the pointer leaves the badge', () => {
    const toggle = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', toggle }));
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
    expect(toggle).not.toHaveBeenCalled();
  });

  it('a touch press is cancellable too and suppresses the native selection', () => {
    const toggle = vi.fn();
    useVoiceMode.mockReturnValue(vm({ state: 'listening', toggle }));
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
    expect(toggle).not.toHaveBeenCalled();
  });

  it('hints to hold while speaking instead of interrupting', async () => {
    useVoiceMode.mockReturnValue(vm({ state: 'speaking', isSpeaking: true }));
    const { user } = renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.speaking' }));
    expect(toast.info).toHaveBeenCalledWith('chat.voice_mode.hold_to_disable');
  });

  it('shows the initializing state while the wake word is still loading', () => {
    useVoiceMode.mockReturnValue(
      vm({ state: 'listening', isListening: true, isKwsListening: false, isKwsSupported: true })
    );
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice_mode.badge_initializing' })).toBeTruthy();
  });

  it('skips the initializing state when the wake word is unsupported', () => {
    // No SharedArrayBuffer/WASM: voice still works tap-to-speak, so the badge
    // must NOT sit in a permanent "initializing" state.
    useVoiceMode.mockReturnValue(
      vm({ state: 'listening', isListening: true, isKwsListening: false, isKwsSupported: false })
    );
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice_mode.click_to_speak' })).toBeTruthy();
  });

  it('is disabled when the browser does not support voice capture', () => {
    useVoiceMode.mockReturnValue(vm({ isSupported: false }));
    renderWithProviders(<VoiceModeBadge onTranscription={vi.fn()} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when the caller disables it', () => {
    useVoiceMode.mockReturnValue(vm({ state: 'listening' }));
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

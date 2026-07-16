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
});

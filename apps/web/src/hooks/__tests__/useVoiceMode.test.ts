/**
 * useVoiceMode — full state machine without any real audio.
 *
 * All audio layers are mocked or faked: the wake word (`useWakeWord`, its
 * captured options let tests fire a detection; its hand-off returns a live
 * stream while it listens), VoiceInputService (captured callbacks let tests
 * deliver transcriptions / connection drops), VoiceActivityDetector
 * (captured onSpeechEnd), AudioContext / AudioWorkletNode / getUserMedia
 * (jsdom fakes). The voiceModeStore is REAL — its own unit suite already
 * pins its transitions; here we exercise the orchestration on top of it.
 *
 * Machine under test:
 *   idle → listening → recording → processing → speaking → listening
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import {
  VOICE_MODE_MAX_RECORDING_SECONDS,
  VOICE_RECORDING_SETUP_TIMEOUT_MS,
} from '@/lib/constants';

// ---------------------------------------------------------------------------
// Hoisted capture state for module mocks
// ---------------------------------------------------------------------------

type ServiceCallbacks = {
  onTranscription: (text: string, duration: number, meta?: Record<string, unknown>) => void;
  onConnectionChange: (connected: boolean) => void;
  onError: (error: Error) => void;
};

const h = vi.hoisted(() => ({
  services: [] as Array<{
    callbacks: ServiceCallbacks;
    isConnected: boolean;
    connect: ReturnType<typeof vi.fn>;
    sendAudio: ReturnType<typeof vi.fn>;
    endAudio: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
    updateCallbacks: ReturnType<typeof vi.fn>;
  }>,
  vads: [] as Array<{
    options: Record<string, unknown>;
    callbacks: { onSpeechEnd?: () => void };
    process: ReturnType<typeof vi.fn>;
    reset: ReturnType<typeof vi.fn>;
    forceEnd: ReturnType<typeof vi.fn>;
  }>,
  wakeOptions: null as {
    language: string;
    enabled: boolean;
    onDetected: () => void | Promise<void>;
    onCommand?: (command: 'stop') => void;
  } | null,
  /** What the wake word reports while enabled ('unavailable' whatever). */
  wake: { state: 'listening' as 'listening' | 'loading' | 'unavailable' },
  handOff: vi.fn(),
  playReadyChime: vi.fn(),
}));

vi.mock('@/lib/voice-input-service', () => ({
  VoiceInputService: class {
    callbacks: ServiceCallbacks;
    isConnected = false;
    connect = vi.fn(async () => {
      this.isConnected = true;
    });
    sendAudio = vi.fn();
    endAudio = vi.fn();
    dispose = vi.fn();
    updateCallbacks = vi.fn((cbs: ServiceCallbacks) => {
      this.callbacks = cbs;
    });

    constructor(callbacks: ServiceCallbacks) {
      this.callbacks = callbacks;
      h.services.push(this as never);
    }
  },
}));

vi.mock('@/lib/audio/vad', () => ({
  VoiceActivityDetector: class {
    options: Record<string, unknown>;
    callbacks: { onSpeechEnd?: () => void };
    process = vi.fn();
    reset = vi.fn();
    forceEnd = vi.fn();

    constructor(options: Record<string, unknown>, callbacks: { onSpeechEnd?: () => void }) {
      this.options = options;
      this.callbacks = callbacks;
      h.vads.push(this as never);
    }
  },
}));

vi.mock('@/lib/audio/ready-chime', () => ({
  playReadyChime: (...args: unknown[]) => h.playReadyChime(...args),
}));

vi.mock('@/hooks/useWakeWord', () => ({
  useWakeWord: (opts: NonNullable<typeof h.wakeOptions>) => {
    h.wakeOptions = opts;
    const state =
      h.wake.state === 'unavailable' ? 'unavailable' : opts.enabled ? h.wake.state : 'idle';
    return {
      state,
      phrase: state === 'listening' ? 'Dis LIA' : null,
      commands: state === 'listening' ? ['stop'] : [],
      error: null,
      handOff: h.handOff,
    };
  },
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { useVoiceMode, type UseVoiceModeOptions } from '../useVoiceMode';
import { useLiveStore } from '@/stores/liveStore';
import { IDLE_RADIO_VIEW, useRadioStore } from '@/stores/radioStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';

// ---------------------------------------------------------------------------
// jsdom audio fakes
// ---------------------------------------------------------------------------

function makeFakeStream(): MediaStream {
  const track = { stop: vi.fn() };
  return { active: true, getTracks: () => [track] } as unknown as MediaStream;
}

class FakeAudioContext {
  sampleRate: number;
  audioWorklet = { addModule: vi.fn(async () => {}) };
  close = vi.fn(async () => {});
  createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));

  constructor(options?: { sampleRate?: number }) {
    this.sampleRate = options?.sampleRate ?? 16000;
  }
}

const workletNodes: Array<{
  name: string;
  port: {
    onmessage: ((event: { data: unknown }) => void) | null;
    postMessage: ReturnType<typeof vi.fn>;
  };
  disconnect: ReturnType<typeof vi.fn>;
}> = [];

class FakeAudioWorkletNode {
  name: string;
  port = { onmessage: null as ((event: { data: unknown }) => void) | null, postMessage: vi.fn() };
  disconnect = vi.fn();

  constructor(_ctx: unknown, name: string) {
    this.name = name;
    workletNodes.push(this as never);
  }
}

let getUserMedia: ReturnType<typeof vi.fn>;

function resetStore(): void {
  useVoiceModeStore.setState({
    isEnabled: false,
    state: 'idle',
    error: null,
    lastWakeWordTime: null,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetStore();
  h.services.length = 0;
  h.vads.length = 0;
  workletNodes.length = 0;
  h.wake.state = 'listening';
  h.wakeOptions = null;
  // While it listens, the wake word holds a live stream it hands over once.
  h.handOff.mockImplementation(async () =>
    h.wake.state === 'listening' && h.wakeOptions?.enabled ? makeFakeStream() : null
  );

  getUserMedia = vi.fn(async () => makeFakeStream());
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
  vi.stubGlobal('AudioContext', FakeAudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode);
  URL.createObjectURL = vi.fn(() => 'blob:fake-worklet');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

/** Render the hook, enable voice mode and flush the async pre-warm effect. */
async function renderEnabled(options: UseVoiceModeOptions = {}) {
  const rendered = renderHook(() => useVoiceMode(options));
  act(() => {
    rendered.result.current.enable();
  });
  await act(async () => {});
  return rendered;
}

/** Fire the wake word and flush the async startRecording pipeline. */
async function triggerWakeWord(): Promise<void> {
  await act(async () => {
    await h.wakeOptions!.onDetected();
  });
}

/** The recording service is the one whose callbacks were (re)wired last. */
function activeService() {
  const service = h.services.at(-1)!;
  const rewired = service.updateCallbacks.mock.calls.at(-1)?.[0] as ServiceCallbacks | undefined;
  return { service, callbacks: rewired ?? service.callbacks };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useVoiceMode — enable / wake-word listening', () => {
  it('enable asks the wake word to listen, in the interface language, and pre-warms the WebSocket', async () => {
    const { result } = await renderEnabled();

    expect(result.current.isEnabled).toBe(true);
    expect(result.current.state).toBe('listening');
    expect(result.current.isListening).toBe(true);
    expect(h.wakeOptions).toMatchObject({ language: 'fr', enabled: true });
    expect(result.current.wakeWordState).toBe('listening');
    expect(result.current.wakePhrase).toBe('Dis LIA');
    // The wake word owns its microphone: the mode opens none while it waits.
    expect(getUserMedia).not.toHaveBeenCalled();
    // WebSocket pre-warmed in the background for lower recording latency.
    expect(h.services).toHaveLength(1);
    expect(h.services[0].isConnected).toBe(true);
  });

  it('pre-warms nothing when the wake word is unavailable (tap-to-speak only)', async () => {
    h.wake.state = 'unavailable';
    const { result } = await renderEnabled();

    expect(result.current.state).toBe('listening');
    expect(result.current.wakeWordState).toBe('unavailable');
    expect(h.services).toHaveLength(0);
  });

  it('stands aside while a live session holds the microphone (ADR-299)', async () => {
    useLiveStore.getState().begin('s1');
    useLiveStore.getState().apply('minted');
    useLiveStore.getState().apply('setup_complete');
    try {
      const { result } = await renderEnabled();
      expect(result.current.state).toBe('listening');
      expect(h.wakeOptions?.enabled).toBe(false);
      expect(result.current.wakeWordState).toBe('idle');
      expect(h.services).toHaveLength(0);
    } finally {
      useLiveStore.getState().reset();
    }
  });

  it('stands aside while the radio plays: its host saying the name must not wake LIA (ADR-324)', async () => {
    useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'playing', sessionId: 'r1' });
    try {
      const { result } = await renderEnabled();
      expect(result.current.state).toBe('listening');
      expect(h.wakeOptions?.enabled).toBe(false);
      expect(h.services).toHaveLength(0);
    } finally {
      useRadioStore.getState().setView(IDLE_RADIO_VIEW);
    }
  });

  it('stops asking the wake word to listen once the mode leaves the listening state', async () => {
    await renderEnabled();
    await triggerWakeWord(); // → recording
    expect(h.wakeOptions?.enabled).toBe(false);
  });

  it('refuses to enable without browser audio support', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined });
    const onError = vi.fn();
    const { result } = renderHook(() => useVoiceMode({ onError }));

    act(() => {
      result.current.enable();
    });

    expect(result.current.isEnabled).toBe(false);
    expect(result.current.state).toBe('idle');
    expect(result.current.error?.message).toContain('not supported');
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('toggle enables then disables the voice mode', async () => {
    const { result } = renderHook(() => useVoiceMode());

    act(() => {
      result.current.toggle();
    });
    expect(result.current.isEnabled).toBe(true);

    await act(async () => {});
    act(() => {
      result.current.toggle();
    });
    expect(result.current.isEnabled).toBe(false);
    expect(result.current.state).toBe('idle');
  });
});

describe('useVoiceMode — wake word → recording', () => {
  it('starts recording on the wake word with the live stream of the detector (no getUserMedia)', async () => {
    const { result } = await renderEnabled();

    await triggerWakeWord();

    expect(result.current.state).toBe('recording');
    expect(result.current.isRecording).toBe(true);
    expect(useVoiceModeStore.getState().lastWakeWordTime).not.toBeNull();
    // The wake word's stream is handed over: no permission round trip at all.
    expect(h.handOff).toHaveBeenCalledTimes(1);
    expect(getUserMedia).not.toHaveBeenCalled();
    // Wake-word flow plays the ready chime.
    expect(h.playReadyChime).toHaveBeenCalledTimes(1);
    // The recording pipeline wired a voice-mode worklet and a VAD.
    expect(workletNodes.some(n => n.name === 'voice-mode-processor')).toBe(true);
    expect(h.vads).toHaveLength(1);
  });

  it("cuts LIA's voice the moment the phrase is heard, before the recording opens", async () => {
    const order: string[] = [];
    h.handOff.mockImplementationOnce(async () => {
      order.push('handOff');
      return makeFakeStream();
    });
    const onInterrupt = vi.fn(() => order.push('voice cut'));
    await renderEnabled({ onInterrupt });

    await triggerWakeWord();

    // Talking over LIA is the barge-in: her voice stops, the person is heard.
    expect(onInterrupt).toHaveBeenCalledTimes(1);
    expect(order).toEqual(['voice cut', 'handOff']);
  });

  it("a spoken « Stop » cuts LIA's voice and nothing else: no recording, no message", async () => {
    const onInterrupt = vi.fn();
    const onTranscription = vi.fn();
    const { result } = await renderEnabled({ onInterrupt, onTranscription });
    expect(result.current.stopWord).toBe('Stop');

    act(() => h.wakeOptions!.onCommand?.('stop'));

    expect(onInterrupt).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('listening');
    expect(h.handOff).not.toHaveBeenCalled();
    expect(h.playReadyChime).not.toHaveBeenCalled();
    expect(onTranscription).not.toHaveBeenCalled();
  });

  it('names no stop word where the loaded model ships none', async () => {
    h.wake.state = 'unavailable';
    const { result } = await renderEnabled();
    expect(result.current.stopWord).toBeNull();
  });

  it('reuses the pre-warmed WebSocket service and rewires its callbacks', async () => {
    await renderEnabled();
    const prewarmed = h.services[0];

    await triggerWakeWord();

    // No new service was created — the pre-warmed one was taken over.
    expect(h.services).toHaveLength(1);
    expect(prewarmed.updateCallbacks).toHaveBeenCalledTimes(1);
    expect(prewarmed.dispose).not.toHaveBeenCalled();
  });

  it('ignores the wake word outside the listening state', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord(); // → recording
    h.playReadyChime.mockClear();

    await triggerWakeWord(); // second wake word while recording

    expect(result.current.state).toBe('recording');
    expect(h.playReadyChime).not.toHaveBeenCalled();
  });

  it('a tap while the wake word listens takes its stream too (no chime)', async () => {
    const { result } = await renderEnabled();

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.state).toBe('recording');
    expect(h.handOff).toHaveBeenCalledTimes(1);
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(h.playReadyChime).not.toHaveBeenCalled();
  });

  it('a tap without the wake word acquires its own microphone (no chime)', async () => {
    h.wake.state = 'unavailable';
    const { result } = await renderEnabled();

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.state).toBe('recording');
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(h.playReadyChime).not.toHaveBeenCalled();
  });

  it('feeds worklet audio chunks to both the VAD and the WebSocket', async () => {
    await renderEnabled();
    await triggerWakeWord();

    const recordingNode = workletNodes.find(n => n.name === 'voice-mode-processor')!;
    const float32 = new Float32Array([0.1, 0.2]).buffer;
    const int16 = new Int16Array([100, 200]).buffer;
    recordingNode.port.onmessage!({ data: { float32, int16 } });

    expect(h.vads[0].process).toHaveBeenCalledTimes(1);
    expect(activeService().service.sendAudio).toHaveBeenCalledWith(int16);
  });

  it('surfaces a clear error when the microphone permission is denied', async () => {
    h.wake.state = 'unavailable';
    const onError = vi.fn();
    const { result } = await renderEnabled({ onError });
    const denied = new Error('denied');
    denied.name = 'NotAllowedError';
    getUserMedia.mockRejectedValue(denied);

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.error?.message).toBe('Microphone permission denied');
    expect(onError).toHaveBeenCalledTimes(1);
    // Error recovery: back to listening (voice mode still enabled).
    expect(result.current.state).toBe('listening');
  });
});

describe('useVoiceMode — recording → processing → speaking → listening', () => {
  it('VAD speech-end moves to processing and finalizes the audio upload', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord();

    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });

    expect(result.current.state).toBe('processing');
    expect(result.current.isProcessing).toBe(true);
    expect(activeService().service.endAudio).toHaveBeenCalledTimes(1);
  });

  it('stopRecording (manual) forces the VAD end and moves to processing', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord();

    act(() => {
      result.current.stopRecording();
    });

    expect(result.current.state).toBe('processing');
    expect(h.vads[0].forceEnd).toHaveBeenCalledTimes(1);
    expect(activeService().service.endAudio).toHaveBeenCalledTimes(1);
  });

  it('stopRecording is a no-op outside the recording state', async () => {
    const { result } = await renderEnabled();

    act(() => {
      result.current.stopRecording();
    });

    expect(result.current.state).toBe('listening');
  });

  it('stops the recording automatically at the max-duration timeout', async () => {
    vi.useFakeTimers();
    h.wake.state = 'unavailable';
    const { result } = await renderEnabled();
    await act(async () => {
      await result.current.startRecording();
    });
    expect(result.current.state).toBe('recording');

    act(() => {
      vi.advanceTimersByTime(VOICE_MODE_MAX_RECORDING_SECONDS * 1000);
    });

    expect(result.current.state).toBe('processing');
  });

  it('disarms the setup timeout once recording started (wake-word flow, no orphan rejection)', async () => {
    // Regression guard (2026-07 audit fix): in the wake-word + pre-warmed-WS
    // flow neither Promise.race consumed the setup-timeout promise, so its
    // rejection fired ~10s after every recording as an unhandled rejection
    // (vitest fails the run on those). The timer must be disarmed once the
    // stream is secured.
    vi.useFakeTimers();
    const { result } = await renderEnabled();
    await triggerWakeWord();
    expect(result.current.state).toBe('recording');

    act(() => {
      vi.advanceTimersByTime(VOICE_RECORDING_SETUP_TIMEOUT_MS + 1000);
    });

    // Still recording, and no unhandled rejection was left behind.
    expect(result.current.state).toBe('recording');
  });

  it('delivers the transcription and enters speaking when TTS callbacks are wired', async () => {
    const onTranscription = vi.fn();
    const onStartSpeaking = vi.fn();
    const { result } = await renderEnabled({ onTranscription, onStartSpeaking });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });

    const meta = { stt_provider: 'elevenlabs', stt_cost_eur: 0.001 };
    act(() => {
      activeService().callbacks.onTranscription('allume le salon', 2.4, meta);
    });

    expect(onTranscription).toHaveBeenCalledWith('allume le salon', meta);
    expect(onStartSpeaking).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('speaking');
    expect(result.current.isSpeaking).toBe(true);
    expect(activeService().service.dispose).toHaveBeenCalled(); // service cleaned up
  });

  it('returns straight to listening when no TTS callback is provided', async () => {
    const onTranscription = vi.fn();
    const { result } = await renderEnabled({ onTranscription });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });

    act(() => {
      activeService().callbacks.onTranscription('bonjour', 1.1);
    });

    expect(onTranscription).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('listening');
  });

  it('discards an empty transcription and resumes listening', async () => {
    const onTranscription = vi.fn();
    const { result } = await renderEnabled({ onTranscription, onStartSpeaking: vi.fn() });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });

    act(() => {
      activeService().callbacks.onTranscription('   ', 0.4);
    });

    expect(onTranscription).not.toHaveBeenCalled();
    expect(result.current.state).toBe('listening');
  });

  it('onTtsComplete closes the loop back to listening while enabled', async () => {
    const onStopSpeaking = vi.fn();
    const { result } = await renderEnabled({ onStartSpeaking: vi.fn(), onStopSpeaking });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });
    act(() => {
      activeService().callbacks.onTranscription('ok', 1);
    });
    expect(result.current.state).toBe('speaking');

    act(() => {
      result.current.onTtsComplete();
    });

    expect(onStopSpeaking).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('listening');
  });

  it('onTtsComplete resets to idle when the voice mode was disabled meanwhile', async () => {
    const { result } = await renderEnabled({ onStartSpeaking: vi.fn() });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });
    act(() => {
      activeService().callbacks.onTranscription('ok', 1);
    });

    act(() => {
      useVoiceModeStore.setState({ isEnabled: false });
    });
    act(() => {
      result.current.onTtsComplete();
    });

    expect(result.current.state).toBe('idle');
  });

  it('recovers to listening when the WebSocket drops during processing', async () => {
    // Regression guard (2026-07 audit fix): the service callbacks are wired
    // once in startRecording, so the connection-drop guard must read the
    // CURRENT machine state (store), not the render-time closure — otherwise
    // the drop is silently ignored and the UI stays stuck on 'processing'.
    const onError = vi.fn();
    const { result } = await renderEnabled({ onError });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });
    expect(result.current.state).toBe('processing');

    act(() => {
      activeService().callbacks.onConnectionChange(false);
    });

    expect(result.current.state).toBe('listening');
    expect(result.current.error?.message).toContain('Connection lost');
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('a reconnection event during processing is not treated as a drop', async () => {
    const onError = vi.fn();
    const { result } = await renderEnabled({ onError });
    await triggerWakeWord();
    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });

    act(() => {
      activeService().callbacks.onConnectionChange(true);
    });

    expect(result.current.state).toBe('processing');
    expect(onError).not.toHaveBeenCalled();
  });
});

describe('useVoiceMode — degraded paths', () => {
  it('an unavailable wake word leaves the mode usable by tap', async () => {
    h.wake.state = 'unavailable';
    const { result } = await renderEnabled();

    expect(result.current.isEnabled).toBe(true); // voice mode survives
    expect(result.current.error).toBeNull();
    await act(async () => {
      await result.current.startRecording();
    });
    expect(result.current.state).toBe('recording');
  });

  it('ignores a second startRecording while one is already active', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord();
    const audioContextCalls = workletNodes.length;

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.state).toBe('recording');
    expect(workletNodes.length).toBe(audioContextCalls); // no new pipeline
  });

  it('discards an inactive stream passed to startRecording and acquires a fresh mic', async () => {
    h.wake.state = 'unavailable';
    const { result } = await renderEnabled();
    const deadTrack = { stop: vi.fn() };
    const deadStream = { active: false, getTracks: () => [deadTrack] } as unknown as MediaStream;

    await act(async () => {
      // The public interface types startRecording as parameterless — the
      // existingStream parameter is internal to the wake-word flow.
      await (result.current.startRecording as (s?: MediaStream) => Promise<void>)(deadStream);
    });

    expect(deadTrack.stop).toHaveBeenCalledTimes(1);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('recording');
  });

  it('a failed WebSocket pre-warm is non-fatal: recording creates its own service', async () => {
    // Make the FIRST service (the pre-warm attempt of the listening state)
    // fail its connection; the wake-word recording must then spin up a new one.
    const originalPush = h.services.push.bind(h.services);
    h.services.push = service => {
      if (h.services.length === 0) {
        service.connect.mockRejectedValue(new Error('prewarm refused'));
      }
      return originalPush(service);
    };
    const { result } = await renderEnabled();
    h.services.push = originalPush;
    expect(h.services[0].isConnected).toBe(false);

    await triggerWakeWord();

    expect(result.current.state).toBe('recording');
    expect(h.services).toHaveLength(2); // fresh service replaced the failed pre-warm
    expect(h.services[1].isConnected).toBe(true);
  });

  it('ignores a late VAD speech-end once already processing', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord();

    act(() => {
      h.vads[0].callbacks.onSpeechEnd!();
    });
    expect(result.current.state).toBe('processing');
    const { service } = activeService();
    const endAudioCalls = service.endAudio.mock.calls.length;

    act(() => {
      h.vads[0].callbacks.onSpeechEnd!(); // late duplicate
    });

    expect(result.current.state).toBe('processing');
    expect(service.endAudio).toHaveBeenCalledTimes(endAudioCalls);
  });

  it('startRecording without browser support raises a clean error', async () => {
    // isSupported is computed at render time — remove the API BEFORE mounting.
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined });
    const onError = vi.fn();
    const { result } = renderHook(() => useVoiceMode({ onError }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.error?.message).toContain('not supported');
    expect(onError).toHaveBeenCalledTimes(1);
    // Regression guard (2026-07 audit fix): with voice mode disabled, error
    // recovery must settle on 'idle' — never the inconsistent pair
    // state='listening' / isEnabled=false.
    expect(result.current.state).toBe('idle');
    expect(result.current.isEnabled).toBe(false);
  });

  it('releases a handed stream when the recording cannot start (never a live microphone left behind)', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord(); // → recording
    const handed = makeFakeStream();

    await act(async () => {
      // A second start while recording returns early: the stream it was
      // handed must not stay open.
      await (result.current.startRecording as (s?: MediaStream) => Promise<void>)(handed);
    });

    expect(result.current.state).toBe('recording');
    expect(handed.getTracks()[0].stop).toHaveBeenCalledTimes(1);
  });

  it('releases the wake word stream when the WebSocket cannot connect', async () => {
    const handed = makeFakeStream();
    h.handOff.mockImplementationOnce(async () => handed);
    // No pre-warmed service, and every connection is refused.
    const originalPush = h.services.push.bind(h.services);
    h.services.push = service => {
      service.connect.mockRejectedValue(new Error('WS refused'));
      return originalPush(service);
    };
    const onError = vi.fn();
    const { result } = await renderEnabled({ onError });

    await triggerWakeWord();
    h.services.push = originalPush;

    expect(result.current.state).toBe('listening');
    expect(onError).toHaveBeenCalledTimes(1);
    expect(handed.getTracks()[0].stop).toHaveBeenCalledTimes(1);
  });

  it('fails over to listening when the WebSocket connect fails during manual setup', async () => {
    h.wake.state = 'unavailable'; // manual flow, no pre-warmed service
    const onError = vi.fn();
    const { result } = await renderEnabled({ onError });
    // The service created by startRecording must fail its connect.
    const originalPush = h.services.push.bind(h.services);
    h.services.push = service => {
      service.connect.mockRejectedValue(new Error('WS refused'));
      return originalPush(service);
    };

    await act(async () => {
      await result.current.startRecording();
    });
    h.services.push = originalPush;

    expect(result.current.state).toBe('listening');
    expect(result.current.error?.message).toBe('WS refused');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

describe('useVoiceMode — disable and cleanup', () => {
  it('disable tears everything down and returns to idle', async () => {
    const { result } = await renderEnabled();
    await triggerWakeWord();
    const { service } = activeService();

    act(() => {
      result.current.disable();
    });

    expect(result.current.isEnabled).toBe(false);
    expect(result.current.state).toBe('idle');
    expect(h.wakeOptions?.enabled).toBe(false);
    expect(service.dispose).toHaveBeenCalled();
  });

  it('unmount disposes the audio pipeline and the WebSocket service', async () => {
    const { unmount } = await renderEnabled();
    await triggerWakeWord();
    const { service } = activeService();

    unmount();

    expect(service.dispose).toHaveBeenCalled();
  });
});

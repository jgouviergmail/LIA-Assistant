/**
 * useVoiceInput — the push-to-talk state machine.
 *
 * `VoiceInputService` is stubbed (it is a unit of its own, covered by
 * `lib/__tests__/voice-input-service.test.ts`); the microphone and the audio
 * graph are stubbed because jsdom has neither. What is driven here is the logic
 * that belongs to the hook and nothing else:
 *
 *  - the **cancellation race**: releasing the button while the connection is
 *    still being set up must abort the startup instead of arming a recording
 *    the user no longer wants;
 *  - the **pre-warmed connection** is reused rather than re-dialled, and a
 *    pre-warm failure is non-fatal;
 *  - every exit path **releases the microphone** — a stream left running keeps
 *    the browser recording indicator on;
 *  - a double press cannot start two recordings.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

interface ServiceConfig {
  onTranscription: (text: string, duration: number, meta?: unknown) => void;
  onConnectionChange?: (connected: boolean) => void;
  onError?: (error: Error) => void;
}

/**
 * A stub of the WebSocket service, declared through `vi.hoisted` so the class
 * exists before the (hoisted) `vi.mock` factory runs.
 */
const { FakeService } = vi.hoisted(() => {
  class FakeService {
    static instances: FakeService[] = [];
    static connectBehaviour: 'resolve' | 'reject' = 'resolve';

    isConnected = false;
    disposed = false;
    endedAudio = false;
    config: ServiceConfig;

    constructor(config: ServiceConfig) {
      this.config = config;
      FakeService.instances.push(this);
    }

    async connect() {
      if (FakeService.connectBehaviour === 'reject') throw new Error('ws refused');
      this.isConnected = true;
    }

    updateCallbacks(config: Partial<ServiceConfig>) {
      this.config = { ...this.config, ...config };
    }

    sendAudio() {}

    endAudio() {
      this.endedAudio = true;
    }

    disconnect() {
      this.isConnected = false;
    }

    dispose() {
      this.disposed = true;
      this.isConnected = false;
    }
  }
  return { FakeService };
});

vi.mock('@/lib/voice-input-service', () => ({ VoiceInputService: FakeService }));

import { useVoiceInput } from '../useVoiceInput';

// --- browser audio stubs -----------------------------------------------------

const trackStop = vi.fn();
const contextClose = vi.fn().mockResolvedValue(undefined);
const nodeDisconnect = vi.fn();
const revokeObjectURL = vi.fn();

function makeStream() {
  return { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream;
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  sampleRate = 16_000;
  audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };

  constructor() {
    FakeAudioContext.instances.push(this);
  }

  createMediaStreamSource() {
    return { connect: vi.fn(), disconnect: nodeDisconnect };
  }

  close() {
    return contextClose();
  }
}

class FakeAudioWorkletNode {
  port = { onmessage: null as ((e: MessageEvent) => void) | null, postMessage: vi.fn() };
  connect = vi.fn();
  disconnect = nodeDisconnect;
}

const getUserMedia = vi.fn();

/** Installs a working microphone + audio graph. */
function installAudio() {
  getUserMedia.mockResolvedValue(makeStream());
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia },
    configurable: true,
  });
  vi.stubGlobal('AudioContext', FakeAudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode);
  Object.defineProperty(URL, 'createObjectURL', {
    value: vi.fn(() => 'blob:worklet'),
    configurable: true,
  });
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
}

const service = (index = -1) =>
  index < 0
    ? FakeService.instances[FakeService.instances.length - 1]
    : FakeService.instances[index];

/** Mounts the hook and waits for the background pre-warm to settle. */
async function setup(options: Parameters<typeof useVoiceInput>[0] = {}) {
  const rendered = renderHook(() => useVoiceInput(options));
  await waitFor(() => expect(FakeService.instances.length).toBeGreaterThan(0));
  return rendered;
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeService.instances = [];
  FakeService.connectBehaviour = 'resolve';
  FakeAudioContext.instances = [];
  installAudio();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('useVoiceInput — capability detection', () => {
  it('reports support when the browser has a microphone and an audio context', async () => {
    const { result } = await setup();

    expect(result.current.isSupported).toBe(true);
    expect(result.current.state).toBe('idle');
  });

  it('reports no support and never opens the microphone without mediaDevices', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
    const onError = vi.fn();
    const { result } = renderHook(() => useVoiceInput({ onError }));

    expect(result.current.isSupported).toBe(false);

    await act(async () => {
      await result.current.startRecording();
    });

    expect(getUserMedia).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('not supported') })
    );
    expect(result.current.state).toBe('idle');
  });
});

describe('useVoiceInput — pre-warming', () => {
  it('opens a connection in the background while idle', async () => {
    await setup();

    await waitFor(() => expect(service().isConnected).toBe(true));
  });

  it('reuses the pre-warmed connection instead of dialling again', async () => {
    const { result } = await setup();
    await waitFor(() => expect(service().isConnected).toBe(true));
    const prewarmed = service();

    await act(async () => {
      await result.current.startRecording();
    });

    // No second service was constructed: the warm socket carried the recording.
    expect(FakeService.instances).toHaveLength(1);
    expect(prewarmed.disposed).toBe(false);
    expect(result.current.state).toBe('recording');
  });

  it('records anyway when the pre-warm never connected', async () => {
    FakeService.connectBehaviour = 'reject';
    const { result } = await setup();

    FakeService.connectBehaviour = 'resolve';
    await act(async () => {
      await result.current.startRecording();
    });

    // A failed pre-warm is non-critical: a fresh service is built on demand.
    expect(FakeService.instances.length).toBeGreaterThan(1);
    expect(result.current.state).toBe('recording');
  });
});

describe('useVoiceInput — recording', () => {
  it('arms the microphone with the expected capture settings', async () => {
    const { result } = await setup();

    await act(async () => {
      await result.current.startRecording();
    });

    expect(getUserMedia).toHaveBeenCalledWith(
      expect.objectContaining({
        audio: expect.objectContaining({ channelCount: 1, echoCancellation: true }),
      })
    );
    expect(result.current.isRecording).toBe(true);
  });

  it('refuses to start a second recording on a double press', async () => {
    const { result } = await setup();
    await act(async () => {
      await result.current.startRecording();
    });
    getUserMedia.mockClear();

    await act(async () => {
      await result.current.startRecording();
    });

    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('sends the audio for transcription and releases the microphone on release', async () => {
    const { result } = await setup();
    await act(async () => {
      await result.current.startRecording();
    });
    const active = service();

    act(() => result.current.stopRecording());

    expect(active.endedAudio).toBe(true);
    expect(result.current.state).toBe('processing');
    // A stream left running keeps the browser recording indicator lit.
    expect(trackStop).toHaveBeenCalled();
    expect(contextClose).toHaveBeenCalled();
  });

  it.each(['idle', 'processing'])('ignores a release while %s', async state => {
    const { result } = await setup();
    if (state === 'processing') {
      await act(async () => {
        await result.current.startRecording();
      });
      act(() => result.current.stopRecording());
    }
    const before = result.current.state;

    act(() => result.current.stopRecording());

    expect(result.current.state).toBe(before);
  });
});

describe('useVoiceInput — cancelling during startup', () => {
  it('aborts the startup when the button is released too early', async () => {
    // The microphone never answers: the hook stays in `connecting`.
    let releaseMic: (stream: MediaStream) => void = () => {};
    getUserMedia.mockReturnValue(
      new Promise<MediaStream>(resolve => {
        releaseMic = resolve;
      })
    );
    const { result } = await setup();

    act(() => {
      void result.current.startRecording();
    });
    await waitFor(() => expect(result.current.state).toBe('connecting'));

    act(() => result.current.stopRecording());
    expect(result.current.state).toBe('idle');

    // Even if the microphone answers afterwards, no recording starts.
    await act(async () => {
      releaseMic(makeStream());
    });
    await waitFor(() => expect(result.current.isRecording).toBe(false));
    expect(trackStop).toHaveBeenCalled();
  });
});

describe('useVoiceInput — results and failures', () => {
  it('exposes the transcription and hands it to the caller', async () => {
    const onTranscription = vi.fn();
    const { result } = await setup({ onTranscription });
    await act(async () => {
      await result.current.startRecording();
    });
    const active = service();

    act(() => active.config.onTranscription('bonjour LIA', 2.5, { stt_provider: 'elevenlabs' }));

    expect(result.current.transcription).toBe('bonjour LIA');
    expect(result.current.durationSeconds).toBe(2.5);
    expect(result.current.state).toBe('idle');
    expect(onTranscription).toHaveBeenCalledWith('bonjour LIA', { stt_provider: 'elevenlabs' });
  });

  it('surfaces a service error and returns to idle', async () => {
    const onError = vi.fn();
    const { result } = await setup({ onError });
    await act(async () => {
      await result.current.startRecording();
    });

    act(() => service().config.onError?.(new Error('socket died')));

    expect(result.current.error?.message).toBe('socket died');
    expect(result.current.state).toBe('idle');
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'socket died' }));
  });

  it('reports a microphone the user refused', async () => {
    getUserMedia.mockRejectedValue(new Error('Permission denied'));
    const onError = vi.fn();
    const { result } = await setup({ onError });

    await act(async () => {
      await result.current.startRecording();
    });

    await waitFor(() => expect(result.current.state).toBe('idle'));
    expect(onError).toHaveBeenCalled();
  });
});

describe('useVoiceInput — teardown', () => {
  it('releases everything it holds when the component goes away', async () => {
    const { result, unmount } = await setup();
    await act(async () => {
      await result.current.startRecording();
    });
    const active = service();

    unmount();

    expect(active.disposed).toBe(true);
    expect(trackStop).toHaveBeenCalled();
    expect(contextClose).toHaveBeenCalled();
    // The worklet URL is shared with the meeting recorder and cached per chunk
    // size (`lib/audio/pcm-worklet`, ADR-258): revoking it on unmount would
    // break the other consumer, so the hook deliberately leaves it alive.
    expect(revokeObjectURL).not.toHaveBeenCalledWith('blob:worklet');
  });

  it('disposes a pre-warmed connection that was never used', async () => {
    const { unmount } = await setup();
    await waitFor(() => expect(service().isConnected).toBe(true));
    const prewarmed = service();

    unmount();

    expect(prewarmed.disposed).toBe(true);
  });
});

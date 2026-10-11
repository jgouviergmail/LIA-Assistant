import { vi } from 'vitest';
import { RoutedLivePlayer } from '@/lib/voice-output/live-player';
import { LiveSessionController, type LiveApi, type LivePlayer } from '../session-controller';
import type { LiveTransport } from '../transport';
import type {
  LiveTransportAudio,
  LiveTransportEvents,
  LiveSessionMode,
  LiveSessionStart,
} from '../types';
const SESSION = 'a'.repeat(32);
const START: LiveSessionStart = {
  session_id: SESSION,
  provider: 'gemini',
  model: 'm',
  mode: 'delegated',
  expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
  capabilities: {
    async_delegation: true,
    delivery_scheduling: true,
    reports_idle: false,
    cancels_on_interruption: true,
    configurable_vad: true,
    resumes: true,
    thinking: false,
    direct_tools: true,
    portal_voice: false,
    vendor_billed: false,
  },
  run_id: `live_session_${SESSION}`,
  credential: 'tok-1',
  credential_expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
  connect_deadline_at: new Date(Date.now() + 60_000).toISOString(),
  connection: 'token',
  session_max_minutes: 10,
  idle_timeout_seconds: 10,
  standby_max_seconds: 8 * 3600,
  setup: { model: 'models/m' },
  preferences: {
    interruptions: true,
    end_of_speech: 'normal',
    result_delivery: 'interrupt',
  },
  delegation_tool_name: 'send_to_lia',
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  turn_text_max_chars: 4000,
  rates: {
    pricing_unit: 'per_1m_tokens',
    input_unit_price: 0.75,
    output_unit_price: 4.5,
    audio_input_unit_price: 3,
    audio_output_unit_price: 12,
    usd_eur_rate: 0.9,
  },
  session_budget_eur: null,
};
const CONFIG = {
  session_max_minutes: 10,
  extension_minutes: 10,
  extension_prompt_seconds: 60,
  connect_window_seconds: 60,
  idle_timeout_seconds: 10,
  hidden_grace_seconds: 20,
  standby_max_seconds: 8 * 3600,
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  delegation_tool_name: 'send_to_lia',
  turn_text_max_chars: 4000,
  delegation_lines: { timed_out: 'T', result_cut: 'C', superseded: 'X', empty_request: 'E' },
  direct_lines: { lookup_failed: 'F' },
  tone_lines: { warm: 'W' },
};

/** Only the audio device is fake; the routed output and controller remain real. */
class AudibleDevice implements LivePlayer {
  isSpeaking = false;
  private listener: (speaking: boolean) => void = () => {};
  async warmup() {}
  enqueue() {
    this.speak(true);
  }
  speak(value: boolean) {
    if (value === this.isSpeaking) return;
    this.isSpeaking = value;
    this.listener(value);
  }
  flush() {
    this.speak(false);
  }
  dispose() {
    this.flush();
  }
  onSpeakingChange(listener: (speaking: boolean) => void) {
    this.listener = listener;
  }
}

export function createAvatarSession(
  mode: LiveSessionMode,
  ownership: LiveTransportAudio['ownership']
) {
  let events: LiveTransportEvents = {};
  const device = new AudibleDevice();
  const output = new RoutedLivePlayer(device, () => null);
  const subscription = vi.spyOn(output, 'onSpeakingChange');
  const transport: LiveTransport = {
    isOpen: true,
    audio: { ownership, inputRate: 16000, outputRate: 24000, chunkMs: 20 },
    connect: async (_options, current) => {
      events = current;
      current.onReady?.();
      if (ownership !== 'pcm') current.onRemoteStream?.(new MediaStream());
    },
    sendAudio() {},
    sendText() {},
    answerDelegation() {},
    setInputActive() {},
    close: async () => {},
  };
  let finishLookup: (value: { text: string; ok: boolean }) => void = () => {};
  let finishChat: () => void = () => {};
  const lookup = new Promise<{ text: string; ok: boolean }>(resolve => {
    finishLookup = resolve;
  });
  const chatPending = new Promise<void>(resolve => {
    finishChat = resolve;
  });
  const post = vi.fn(async (url: string): Promise<unknown> => {
    if (url === '/live/sessions') return { ...START, mode };
    if (url.endsWith('/tools')) return lookup;
    if (url.endsWith('/turns')) return { user_message_id: 'u', assistant_message_id: 'a' };
    return { duration_seconds: 0, delegations: 0, voice_turns: 0, extensions: 0, usage: null };
  });
  const api: LiveApi = {
    async get<T>(): Promise<T> {
      return CONFIG as T;
    },
    async post<T>(url: string): Promise<T> {
      return (await post(url)) as T;
    },
  };
  const controller = new LiveSessionController({
    api,
    createTransport: () => transport,
    createPlayer: () => output,
    startMic: async () => ({
      stream: new MediaStream(),
      mute() {},
      stop: async () => {},
      detach: async () => null,
    }),
    isSupported: () => true,
    createWakeListener: () => null,
    wakeLanguage: () => 'fr',
    chime() {},
    chat: {
      sendMessage: async () => chatPending,
      stop: async () => {},
      appendMessage() {},
      readAnswer: async () => ({ text: 'Read-only answer.', pendingQuestion: null }),
    },
  });
  return {
    controller,
    output,
    device,
    events: () => events,
    startSpeech: () =>
      ownership === 'pcm'
        ? events.onAudio?.(new Int16Array([1200, -1200]).buffer)
        : events.onSpeakingChange?.(true),
    stopSpeech: () =>
      ownership === 'pcm' ? device.speak(false) : events.onSpeakingChange?.(false),
    lateSpeech: () => subscription.mock.calls[0][0](true),
    finishWork: () => {
      finishLookup({ text: 'Done.', ok: true });
      finishChat();
    },
  };
}

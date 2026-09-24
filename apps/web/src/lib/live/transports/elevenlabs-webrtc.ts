/** ElevenLabs voice over the vendor SDK's native LiveKit audio tracks. */
import type { VoiceConversation } from '@elevenlabs/client';

import type { LiveTransport } from '../transport';
import type {
  LiveConnectOptions,
  LiveDelivery,
  LiveTransportAudio,
  LiveTransportEvents,
} from '../types';

export const ELEVENLABS_WEBRTC_AUDIO: LiveTransportAudio = {
  ownership: 'managed',
  inputRate: 48000,
  outputRate: 48000,
  chunkMs: 20,
};

function recordOf(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function promptOf(setup: Record<string, unknown>): string {
  const override = recordOf(setup.conversation_config_override);
  const agent = recordOf(override.agent);
  const prompt = recordOf(agent.prompt).prompt;
  if (typeof prompt !== 'string' || !prompt) throw new Error('live_setup_prompt_missing');
  return prompt;
}

export class ElevenLabsWebRtcTransport implements LiveTransport {
  readonly audio = ELEVENLABS_WEBRTC_AUDIO;
  private conversation: VoiceConversation | null = null;
  private events: LiveTransportEvents = {};
  private pending = new Map<string, (result: string) => void>();
  private nextToolId = 0;
  private generation = 0;

  get isOpen(): boolean {
    return this.conversation !== null;
  }

  async connect(options: LiveConnectOptions, events: LiveTransportEvents): Promise<void> {
    this.events = events;
    const generation = ++this.generation;
    const current = () => generation === this.generation;
    const { Conversation } = await import('@elevenlabs/client');
    const declaredTools: Record<string, (parameters: unknown) => Promise<string>> = {};
    for (const name of options.toolNames ?? []) {
      declaredTools[name] = parameters => this.delegate(name, parameters);
    }
    // The agent may also carry the person's own client tools. The pinned SDK
    // checks Object.hasOwn before calling a handler; answer every name through
    // the same LIA tool door, which refuses unknown names safely.
    const clientTools = new Proxy(declaredTools, {
      getOwnPropertyDescriptor: (target, name) =>
        Reflect.getOwnPropertyDescriptor(target, name) ??
        (typeof name === 'string'
          ? { configurable: true, enumerable: false, value: undefined }
          : undefined),
      get: (target, name) =>
        typeof name === 'string'
          ? Object.hasOwn(target, name)
            ? target[name]
            : (parameters: unknown) => this.delegate(name, parameters)
          : undefined,
    });
    const conversation = await Conversation.startSession({
      conversationToken: options.credential,
      connectionType: 'webrtc',
      textOnly: false,
      overrides: { agent: { prompt: { prompt: promptOf(options.setup) } } },
      clientTools,
      onConnect: ({ conversationId }) => {
        if (current()) events.onProviderConversation?.(conversationId);
      },
      onConversationMetadata: metadata => {
        if (current() && metadata.conversation_id) {
          events.onProviderConversation?.(metadata.conversation_id);
        }
      },
      onMessage: ({ role, message }) => {
        if (!current()) return;
        if (role === 'user') events.onTranscript?.('user', message);
        if (role === 'agent') {
          events.onTranscript?.('assistant', message);
          events.onTurnComplete?.();
        }
      },
      onModeChange: ({ mode }) => {
        if (current()) events.onSpeakingChange?.(mode === 'speaking');
      },
      onInterruption: () => {
        if (current()) events.onInterrupted?.();
      },
      onError: message => {
        if (current()) events.onError?.(new Error(message));
      },
      onDisconnect: details => {
        if (!current()) return;
        this.conversation = null;
        this.releasePending();
        const code = 'closeCode' in details ? (details.closeCode ?? 1006) : 1006;
        const reason = 'closeReason' in details ? (details.closeReason ?? '') : '';
        events.onClosed?.(code, reason);
      },
    });
    if (!current()) {
      await conversation.endSession();
      return;
    }
    this.conversation = conversation;
    events.onReady?.();
  }

  private delegate(name: string, parameters: unknown): Promise<string> {
    const id = `sdk-${++this.nextToolId}`;
    const args = recordOf(parameters);
    const request = args.request;
    return new Promise(resolve => {
      this.pending.set(id, resolve);
      void this.events.onDelegation?.([
        {
          id,
          request: typeof request === 'string' ? request : null,
          call: { name, args },
        },
      ]);
    });
  }

  sendAudio(_pcm16: ArrayBuffer): void {
    // The SDK publishes the microphone through LiveKit.
  }

  sendText(text: string): void {
    this.conversation?.sendUserMessage(text);
  }

  answerDelegation(
    id: string,
    result: string,
    _delivery: LiveDelivery,
    note: string | null = null
  ): void {
    const resolve = this.pending.get(id);
    if (!resolve) return;
    this.pending.delete(id);
    resolve(note ? JSON.stringify({ result, tone: note }) : result);
  }

  setInputActive(on: boolean): void {
    this.conversation?.setMicMuted(!on);
  }

  async close(): Promise<void> {
    this.generation += 1;
    this.releasePending();
    const conversation = this.conversation;
    this.conversation = null;
    if (conversation) await conversation.endSession();
  }

  private releasePending(): void {
    for (const resolve of this.pending.values()) resolve('');
    this.pending.clear();
  }
}

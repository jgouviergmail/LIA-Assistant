import { Conversation } from '@elevenlabs/client';
import type { PartialOptions, VoiceConversation } from '@elevenlabs/client';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ElevenLabsWebRtcTransport } from '../transports/elevenlabs-webrtc';
import type { LiveConnectOptions, LiveTransportEvents } from '../types';

vi.mock('@elevenlabs/client', () => ({ Conversation: { startSession: vi.fn() } }));

const options: LiveConnectOptions = {
  credential: 'livekit-token',
  setup: {
    type: 'conversation_initiation_client_data',
    conversation_config_override: { agent: { prompt: { prompt: 'Speak as LIA.' } } },
  },
  toolNames: ['send_to_lia', 'get_events_tool'],
  capabilities: {
    async_delegation: false,
    delivery_scheduling: false,
    reports_idle: false,
    cancels_on_interruption: false,
    configurable_vad: false,
    resumes: false,
    thinking: false,
    direct_tools: true,
    portal_voice: true,
    vendor_billed: true,
  },
};

describe('ElevenLabsWebRtcTransport', () => {
  let sdkOptions: PartialOptions;
  const endSession = vi.fn(async () => {});
  const sendUserMessage = vi.fn();
  const setMicMuted = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(Conversation.startSession).mockImplementation(async incoming => {
      sdkOptions = incoming;
      return { endSession, sendUserMessage, setMicMuted } as unknown as VoiceConversation;
    });
  });

  it('uses native WebRTC audio and preserves the prompt, transcripts, tool results and closure', async () => {
    const transport = new ElevenLabsWebRtcTransport();
    const events: LiveTransportEvents = {
      onReady: vi.fn(),
      onProviderConversation: vi.fn(),
      onTranscript: vi.fn(),
      onTurnComplete: vi.fn(),
      onSpeakingChange: vi.fn(),
      onDelegation: vi.fn(),
      onClosed: vi.fn(),
    };
    await transport.connect(options, events);
    expect(transport.audio.ownership).toBe('managed');
    expect(sdkOptions).toMatchObject({
      conversationToken: 'livekit-token',
      connectionType: 'webrtc',
      overrides: { agent: { prompt: { prompt: 'Speak as LIA.' } } },
    });
    expect(events.onReady).toHaveBeenCalledOnce();
    sdkOptions.onConnect?.({ conversationId: 'conv_42' });
    expect(events.onProviderConversation).toHaveBeenCalledWith('conv_42');
    sdkOptions.onMessage?.({ source: 'user', role: 'user', message: 'Hi' });
    sdkOptions.onMessage?.({ source: 'ai', role: 'agent', message: 'Hello' });
    expect(events.onTranscript).toHaveBeenCalledWith('user', 'Hi');
    expect(events.onTranscript).toHaveBeenCalledWith('assistant', 'Hello');
    expect(events.onTurnComplete).toHaveBeenCalledOnce();
    sdkOptions.onModeChange?.({ mode: 'speaking' });
    expect(events.onSpeakingChange).toHaveBeenCalledWith(true);

    const result = sdkOptions.clientTools?.send_to_lia({ request: 'weather' });
    expect(events.onDelegation).toHaveBeenCalledWith([
      {
        id: 'sdk-1',
        request: 'weather',
        call: { name: 'send_to_lia', args: { request: 'weather' } },
      },
    ]);
    transport.answerDelegation('sdk-1', 'Sunny', 'now', 'warm');
    await expect(result).resolves.toBe('{"result":"Sunny","tone":"warm"}');
    expect(Object.hasOwn(sdkOptions.clientTools ?? {}, 'user_tool')).toBe(true);
    const extra = sdkOptions.clientTools?.user_tool({});
    transport.answerDelegation('sdk-2', 'refused', 'now');
    await expect(extra).resolves.toBe('refused');
    transport.sendText('Continue');
    transport.setInputActive(false);
    expect(sendUserMessage).toHaveBeenCalledWith('Continue');
    expect(setMicMuted).toHaveBeenCalledWith(true);
    await transport.close();
    expect(endSession).toHaveBeenCalledOnce();
    sdkOptions.onDisconnect?.({ reason: 'agent', closeCode: 1000 });
    expect(events.onClosed).not.toHaveBeenCalled();
  });

  it('surfaces an unexpected SDK disconnect', async () => {
    const transport = new ElevenLabsWebRtcTransport();
    const onClosed = vi.fn();
    await transport.connect(options, { onClosed });
    sdkOptions.onDisconnect?.({ reason: 'agent', closeCode: 1006, closeReason: 'lost' });
    expect(onClosed).toHaveBeenCalledWith(1006, 'lost');
    expect(transport.isOpen).toBe(false);
  });
});

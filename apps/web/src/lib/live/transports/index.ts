/**
 * The transport of a provider the API named in `LiveSessionStart.provider`
 * (ADR-299). A provider the browser does not speak is a refusal here, never a
 * silent fallback to another one.
 */
import type { LiveTransport } from '../transport';

import { ElevenLabsLiveTransport } from './elevenlabs-ws';
import { ElevenLabsWebRtcTransport } from './elevenlabs-webrtc';
import { GeminiLiveTransport } from './gemini-ws';
import { OpenAiLiveTransport } from './openai-webrtc';

const FACTORIES: Readonly<Record<string, () => LiveTransport>> = {
  gemini: () => new GeminiLiveTransport(),
  openai: () => new OpenAiLiveTransport(),
  elevenlabs: () => new ElevenLabsLiveTransport(),
};

export function createLiveTransport(
  provider: string,
  audioTransport: 'websocket' | 'webrtc' = 'websocket'
): LiveTransport {
  if (provider === 'elevenlabs' && audioTransport === 'webrtc') {
    return new ElevenLabsWebRtcTransport();
  }
  const factory = FACTORIES[provider];
  if (!factory) throw new Error(`live_provider_unsupported:${provider}`);
  return factory();
}

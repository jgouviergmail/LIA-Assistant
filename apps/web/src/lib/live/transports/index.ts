/**
 * The transport of a provider the API named in `LiveSessionStart.provider`
 * (ADR-299). A provider the browser does not speak is a refusal here, never a
 * silent fallback to another one.
 */
import type { LiveTransport } from '../transport';

import { ElevenLabsLiveTransport } from './elevenlabs-ws';
import { GeminiLiveTransport } from './gemini-ws';
import { OpenAiLiveTransport } from './openai-webrtc';

const FACTORIES: Readonly<Record<string, () => LiveTransport>> = {
  gemini: () => new GeminiLiveTransport(),
  openai: () => new OpenAiLiveTransport(),
  elevenlabs: () => new ElevenLabsLiveTransport(),
};

export function createLiveTransport(provider: string): LiveTransport {
  const factory = FACTORIES[provider];
  if (!factory) throw new Error(`live_provider_unsupported:${provider}`);
  return factory();
}

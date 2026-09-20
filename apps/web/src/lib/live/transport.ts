/**
 * The seam between the session and a provider's wire protocol (ADR-299, spec A2;
 * wave 2 spec A11).
 *
 * A transport speaks INTENTIONS, never frames: open one connection, push the
 * microphone, answer a delegation by delivery mode, tell whether the input is
 * active, close gracefully. It declares its audio (`audio`) so the controller
 * sizes the microphone and the player from it, and it reads the session's
 * CAPABILITIES to shape its wire (Gemini omits `scheduling` where the model
 * refuses it). It knows nothing of the chat, the banner or the store. Gemini
 * speaks JSON over a raw WebSocket and hands PCM over; GPT-Live speaks WebRTC
 * and carries the tracks itself — same interface.
 */
import type {
  LiveConnectOptions,
  LiveDelivery,
  LiveTransportAudio,
  LiveTransportEvents,
} from './types';

export interface LiveTransport {
  readonly isOpen: boolean;
  /** The audio contract this transport works with. */
  readonly audio: LiveTransportAudio;
  /** Resolves once the provider acknowledged the setup; rejects on a close before that. */
  connect(options: LiveConnectOptions, events: LiveTransportEvents): Promise<void>;
  /** A microphone chunk at `audio.inputRate` (pcm ownership; a native transport ignores it). */
  sendAudio(pcm16: ArrayBuffer): void;
  /** A text turn the voice reads as if spoken by the person (a late answer). */
  sendText(text: string): void;
  /**
   * The result of a delegation, delivered as asked — with, when known, the
   * delivery note saying how LIA said it (ADR-253), on the wire's own shape.
   */
  answerDelegation(id: string, result: string, delivery: LiveDelivery, note?: string | null): void;
  /** The microphone is (no longer) feeding the provider: told the provider's own way. */
  setInputActive(on: boolean): void;
  /** Close gracefully; resolves once the provider's own close sequence is done or bounded. */
  close(): Promise<void>;
}

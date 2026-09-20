/**
 * OpenAiLiveTransport — GPT-Live over WebRTC, with the peer connection faked.
 *
 *  - the `oai-events` channel is created BEFORE the offer; the microphone
 *    tracks are added; the offer's SDP goes through `exchangeOffer` with the
 *    credential and the answer is set as the remote description; connect
 *    resolves once the channel is open and reports ready;
 *  - a missing exchange door or a browser without WebRTC refuses before any
 *    peer connection exists;
 *  - `session.delegation.created` carries no text: the request is composed
 *    from the input transcript after the grace; an empty transcript is a
 *    null request;
 *  - a result becomes `commentary.append` (spoken) or `thinking.append`
 *    (silent) on the delegation's id, split under the append bound;
 *  - the assistant's transcript IS its speech: the first delta reports
 *    speaking, its quiet reports the end and one turn complete; the person's
 *    words meanwhile are an interruption;
 *  - mute/unmute are told the provider's way; `close()` asks `session.close`
 *    and waits for `session.closed`, bounded; a `session.closed` or a failed
 *    connection reports closed; an `error` event is reported, never thrown.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  OPENAI_COMPOSE_GRACE_MS,
  OPENAI_EVENTS_CHANNEL,
  OPENAI_LIVE_APPEND_MAX_TOKENS,
  OPENAI_SPEAKING_QUIET_MS,
  OPENAI_STARTED_TIMEOUT_MS,
  OpenAiLiveTransport,
  splitForAppend,
} from '../transports/openai-webrtc';
import type { LiveConnectOptions, LiveModelCapabilities, LiveTransportEvents } from '../types';

const CAPABILITIES: LiveModelCapabilities = {
  async_delegation: true,
  delivery_scheduling: false,
  reports_idle: false,
  cancels_on_interruption: false,
  configurable_vad: false,
  resumes: false,
  thinking: false,
  direct_tools: false,
  portal_voice: false,
  vendor_billed: false,
};

class FakeChannel {
  readyState: 'connecting' | 'open' | 'closing' | 'closed' = 'connecting';
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: Array<Record<string, unknown>> = [];
  constructor(readonly label: string) {}
  send(data: string) {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close() {
    this.readyState = 'closed';
    this.onclose?.();
  }
  open() {
    this.readyState = 'open';
    this.onopen?.();
  }
  emit(event: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

class FakePeer {
  static instances: FakePeer[] = [];
  channels: FakeChannel[] = [];
  tracks: Array<{ track: MediaStreamTrack; stream: MediaStream }> = [];
  localDescription: { type: string; sdp: string } | null = null;
  remoteDescription: { type: string; sdp: string } | null = null;
  iceGatheringState: 'new' | 'gathering' | 'complete' = 'complete';
  connectionState: string = 'new';
  ontrack: ((event: { streams: MediaStream[] }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  closed = false;
  constructor() {
    FakePeer.instances.push(this);
  }
  createDataChannel(label: string) {
    const channel = new FakeChannel(label);
    this.channels.push(channel);
    return channel;
  }
  addTrack(track: MediaStreamTrack, stream: MediaStream) {
    this.tracks.push({ track, stream });
  }
  async createOffer() {
    return { type: 'offer', sdp: 'v=0 offer' };
  }
  async setLocalDescription(description: { type: string; sdp: string }) {
    this.localDescription = description;
  }
  async setRemoteDescription(description: { type: string; sdp: string }) {
    this.remoteDescription = description;
    // The answer set, the channel opens as it would once the peers connect,
    // and the provider says the session started (measured 2026-09-19).
    this.channels[0]?.open();
    this.channels[0]?.emit({ type: 'session.started', session: { id: 'live_1' } });
  }
  addEventListener() {}
  removeEventListener() {}
  close() {
    this.closed = true;
  }
}

function microphone(): MediaStream {
  const track = { kind: 'audio', enabled: true } as unknown as MediaStreamTrack;
  return { getAudioTracks: () => [track] } as unknown as MediaStream;
}

function options(overrides: Partial<LiveConnectOptions> = {}): LiveConnectOptions {
  return {
    credential: 'nonce-1',
    setup: {},
    resumptionHandle: null,
    capabilities: CAPABILITIES,
    microphone: microphone(),
    exchangeOffer: vi.fn(async () => 'v=0 answer'),
    ...overrides,
  };
}

async function connected(
  events: LiveTransportEvents = {},
  overrides: Partial<LiveConnectOptions> = {}
) {
  const transport = new OpenAiLiveTransport();
  const opts = options(overrides);
  await transport.connect(opts, events);
  const peer = FakePeer.instances.at(-1) as FakePeer;
  return { transport, peer, channel: peer.channels[0], opts };
}

describe('OpenAiLiveTransport', () => {
  beforeEach(() => {
    FakePeer.instances = [];
    vi.stubGlobal('RTCPeerConnection', FakePeer);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('creates the events channel before the offer, exchanges the SDP through the API and reports ready', async () => {
    const onReady = vi.fn();
    const { transport, peer, channel, opts } = await connected({ onReady });
    expect(channel.label).toBe(OPENAI_EVENTS_CHANNEL);
    expect(peer.tracks).toHaveLength(1);
    expect(peer.localDescription?.sdp).toBe('v=0 offer');
    expect(opts.exchangeOffer).toHaveBeenCalledWith('nonce-1', 'v=0 offer');
    expect(peer.remoteDescription).toEqual({ type: 'answer', sdp: 'v=0 answer' });
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(transport.isOpen).toBe(true);
  });

  it('is not ready on an open channel alone: the provider must say the session started', async () => {
    class SilentPeer extends FakePeer {
      async setRemoteDescription(description: { type: string; sdp: string }) {
        this.remoteDescription = description;
        this.channels[0]?.open();
      }
    }
    vi.stubGlobal('RTCPeerConnection', SilentPeer);
    const onReady = vi.fn();
    const transport = new OpenAiLiveTransport();
    // The expectation is attached BEFORE the clock moves: a rejection nobody
    // awaits yet would be reported as unhandled.
    const refused = expect(transport.connect(options(), { onReady })).rejects.toThrow(
      'live_session_not_started'
    );
    await vi.advanceTimersByTimeAsync(OPENAI_STARTED_TIMEOUT_MS + 1);
    await refused;
    expect(onReady).not.toHaveBeenCalled();
  });

  it('tears the peer connection down when the exchange is refused', async () => {
    const transport = new OpenAiLiveTransport();
    const refused = vi.fn(async () => {
      throw new Error('credential_invalid');
    });
    await expect(transport.connect(options({ exchangeOffer: refused }), {})).rejects.toThrow(
      'credential_invalid'
    );
    expect(FakePeer.instances).toHaveLength(1);
    expect(FakePeer.instances[0].closed).toBe(true);
    expect(transport.isOpen).toBe(false);
  });

  it('refuses without the exchange door, and without WebRTC, before any peer connection exists', async () => {
    const transport = new OpenAiLiveTransport();
    await expect(transport.connect(options({ exchangeOffer: undefined }), {})).rejects.toThrow(
      'live_offer_exchange_missing'
    );
    vi.stubGlobal('RTCPeerConnection', undefined);
    await expect(transport.connect(options(), {})).rejects.toThrow('unsupported_browser');
    expect(FakePeer.instances).toHaveLength(0);
  });

  it('composes the request from the input transcript after the grace, and null when nothing was said', async () => {
    const onDelegation = vi.fn();
    const onTranscript = vi.fn();
    const { channel } = await connected({ onDelegation, onTranscript });
    channel.emit({
      type: 'session.input_transcript.delta',
      delta: 'what is on ',
      start_ms: 100,
      end_ms: 600,
    });
    channel.emit({
      type: 'session.delegation.created',
      offset_ms: 1500,
      delegation: { id: 'd1', type: 'delegation', target: 'client' },
    });
    // The last fragment lands AFTER the delegation event: the grace catches it.
    channel.emit({
      type: 'session.input_transcript.delta',
      delta: 'my agenda?',
      start_ms: 600,
      end_ms: 1400,
    });
    expect(onDelegation).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(OPENAI_COMPOSE_GRACE_MS);
    expect(onDelegation).toHaveBeenCalledWith([{ id: 'd1', request: 'what is on my agenda?' }]);
    expect(onTranscript).toHaveBeenCalledWith('user', 'what is on ');
    channel.emit({ type: 'session.delegation.created', offset_ms: 3000, delegation: { id: 'd2' } });
    await vi.advanceTimersByTimeAsync(OPENAI_COMPOSE_GRACE_MS);
    expect(onDelegation).toHaveBeenLastCalledWith([{ id: 'd2', request: null }]);
  });

  it('answers a delegation as spoken commentary or silent thinking on its id, split under the bound', async () => {
    const { transport, channel } = await connected();
    transport.answerDelegation('d1', 'Two meetings tomorrow.', 'now');
    // A silent close never carries a note, whatever the bridge hands.
    transport.answerDelegation('d1', 'Nothing to say.', 'silent', 'LIA said this warmly.');
    const long = Array.from({ length: 400 }, (_, i) => `word${i}`).join(' ');
    transport.answerDelegation('d2', long, 'when_idle');
    const sent = channel.sent.map(e => ({ type: e.type, id: e.delegation_id, content: e.content }));
    expect(sent[0]).toEqual({
      type: 'session.commentary.append',
      id: 'd1',
      content: 'Two meetings tomorrow.',
    });
    expect(sent[1]).toEqual({
      type: 'session.thinking.append',
      id: 'd1',
      content: 'Nothing to say.',
    });
    const parts = sent.slice(2);
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.every(p => p.type === 'session.commentary.append' && p.id === 'd2')).toBe(true);
    // This wire has no field for a delivery note: it is a SILENT append
    // before the spoken one, on the same delegation (the mandate says what it is).
    channel.sent.length = 0;
    transport.answerDelegation('d3', 'Done.', 'now', 'LIA said this warmly.');
    expect(
      channel.sent.map(e => ({ type: e.type, id: e.delegation_id, content: e.content }))
    ).toEqual([
      { type: 'session.thinking.append', id: 'd3', content: 'LIA said this warmly.' },
      { type: 'session.commentary.append', id: 'd3', content: 'Done.' },
    ]);
    expect(parts.map(p => p.content).join(' ')).toBe(long);
    expect(channel.sent.every(e => typeof e.event_id === 'string')).toBe(true);
  });

  it('speaks a late answer as commentary on the last delegation', async () => {
    const { transport, channel } = await connected();
    channel.emit({ type: 'session.delegation.created', offset_ms: 10, delegation: { id: 'd9' } });
    transport.sendText('Late answer.');
    expect(channel.sent.at(-1)).toMatchObject({
      type: 'session.commentary.append',
      delegation_id: 'd9',
      content: 'Late answer.',
    });
  });

  it("reads the assistant's speech from its transcript, and the person's words meanwhile as an interruption", async () => {
    const onSpeakingChange = vi.fn();
    const onTurnComplete = vi.fn();
    const onInterrupted = vi.fn();
    const onTranscript = vi.fn();
    const { channel } = await connected({
      onSpeakingChange,
      onTurnComplete,
      onInterrupted,
      onTranscript,
    });
    channel.emit({
      type: 'session.output_transcript.delta',
      delta: 'Two ',
      start_ms: 0,
      end_ms: 200,
    });
    expect(onSpeakingChange).toHaveBeenCalledWith(true);
    expect(onTranscript).toHaveBeenCalledWith('assistant', 'Two ');
    await vi.advanceTimersByTimeAsync(OPENAI_SPEAKING_QUIET_MS / 2);
    channel.emit({
      type: 'session.output_transcript.delta',
      delta: 'meetings.',
      start_ms: 200,
      end_ms: 500,
    });
    channel.emit({
      type: 'session.input_transcript.delta',
      delta: 'wait',
      start_ms: 300,
      end_ms: 400,
    });
    expect(onInterrupted).toHaveBeenCalledTimes(1);
    expect(onTurnComplete).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(OPENAI_SPEAKING_QUIET_MS);
    expect(onSpeakingChange).toHaveBeenLastCalledWith(false);
    expect(onTurnComplete).toHaveBeenCalledTimes(1);
  });

  it('tells the provider about the microphone and ignores PCM (native ownership)', async () => {
    const { transport, channel } = await connected();
    transport.sendAudio(new ArrayBuffer(8));
    transport.setInputActive(false);
    transport.setInputActive(true);
    expect(channel.sent.map(e => e.type)).toEqual([
      'session.input_audio.mute',
      'session.input_audio.unmute',
    ]);
  });

  it('reports session.usage.updated as a duration report (ADR-300 wave 3)', async () => {
    const onUsage = vi.fn();
    const { channel } = await connected({ onUsage });
    channel.emit({
      type: 'session.usage.updated',
      usage: { seconds: 8 },
      context_window: { usage_ratio: 0.12 },
    });
    expect(onUsage).toHaveBeenCalledWith({ duration: { seconds: 8, contextRatio: 0.12 } });
  });

  it('closes gracefully: session.close, then session.closed reports closed and tears down', async () => {
    const onClosed = vi.fn();
    const { transport, channel, peer } = await connected({ onClosed });
    const closing = transport.close();
    expect(channel.sent.at(-1)).toMatchObject({ type: 'session.close' });
    channel.emit({ type: 'session.closed', reason: 'close_requested', usage: { seconds: 12 } });
    await closing;
    expect(onClosed).toHaveBeenCalledWith(1000, 'close_requested');
    expect(peer.closed).toBe(true);
    expect(transport.isOpen).toBe(false);
  });

  it('closes anyway once the bounded wait passes, and a dropped connection reports 1006', async () => {
    const onClosed = vi.fn();
    const { transport, peer } = await connected({ onClosed });
    const closing = transport.close();
    await vi.advanceTimersByTimeAsync(3000);
    await closing;
    expect(peer.closed).toBe(true);
    const dropped = await connected({ onClosed });
    dropped.peer.connectionState = 'failed';
    dropped.peer.onconnectionstatechange?.();
    expect(onClosed).toHaveBeenLastCalledWith(1006, 'failed');
    expect(dropped.transport.isOpen).toBe(false);
  });

  it('reports a provider error and a bad frame without throwing', async () => {
    const onError = vi.fn();
    const { channel } = await connected({ onError });
    channel.emit({ type: 'error', error: { code: 'invalid_request_error', message: 'nope' } });
    channel.onmessage?.({ data: '{not json' });
    expect(onError).toHaveBeenCalledTimes(2);
    expect(String(onError.mock.calls[0][0])).toContain('invalid_request_error: nope');
  });
});

describe('splitForAppend', () => {
  it('keeps a short text whole and cuts a long one at word boundaries under the margin', () => {
    expect(splitForAppend('Two meetings.')).toEqual(['Two meetings.']);
    // ~3 400 characters, ~850 tokens by the estimate: above one append's bound.
    const words = Array.from({ length: 600 }, (_, i) => `w${i}`).join(' ');
    const parts = splitForAppend(words, OPENAI_LIVE_APPEND_MAX_TOKENS);
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.join(' ')).toBe(words);
    // Roughly four characters a token: no part exceeds the bound.
    expect(parts.every(p => p.length / 4 <= OPENAI_LIVE_APPEND_MAX_TOKENS)).toBe(true);
  });

  it('cuts an unbreakable run by characters', () => {
    const run = 'x'.repeat(3000);
    const parts = splitForAppend(run, 100);
    expect(parts.join('')).toBe(run);
    expect(parts.every(p => p.length <= 320)).toBe(true);
  });
});

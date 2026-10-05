import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SimliTransport } from '../simli-transport';
import type { SimliTransportEvents } from '../simli-transport';
import type { AvatarSession } from '../types';
import { logger } from '@/lib/logger';

vi.mock('@/lib/logger', () => ({ logger: { warn: vi.fn(), debug: vi.fn() } }));

class FakeTrack {
  stop = vi.fn();
  constructor(readonly kind: string) {}
}
class FakeStream {
  constructor(readonly tracks: FakeTrack[] = []) {}
  getTracks() {
    return this.tracks;
  }
  addTrack(track: FakeTrack) {
    this.tracks.push(track);
  }
}
class FakePeer {
  static instances: FakePeer[] = [];
  readonly transceivers: { kind: string; direction?: RTCRtpTransceiverDirection }[] = [];
  iceGatheringState = 'complete';
  connectionState = 'new';
  localDescription: RTCSessionDescriptionInit | null = null;
  remoteDescription: RTCSessionDescriptionInit | null = null;
  ontrack: ((event: { track: FakeTrack; streams: FakeStream[] }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  close = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  constructor(readonly config: RTCConfiguration) {
    FakePeer.instances.push(this);
  }
  addTransceiver(kind: string, init: RTCRtpTransceiverInit) {
    this.transceivers.push({ kind, direction: init.direction });
  }
  async createOffer(): Promise<RTCSessionDescriptionInit> {
    return { type: 'offer', sdp: 'v=0\r\na=fixture' };
  }
  async setLocalDescription(description: RTCSessionDescriptionInit) {
    this.localDescription = description;
  }
  async setRemoteDescription(description: RTCSessionDescriptionInit) {
    this.remoteDescription = description;
  }
}
class FakeSocket {
  static instances: FakeSocket[] = [];
  readyState = 0;
  bufferedAmount = 0;
  binaryType = 'blob';
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  emit(data: string) {
    this.onmessage?.({ data });
  }
}
const session: AvatarSession = {
  session_token: 'test-token',
  lease_id: 'fixture-lease',
  ice_servers: [{ urls: 'stun:fixture.invalid' }],
  max_session_seconds: 3600,
};
function events(): SimliTransportEvents {
  return {
    onVideo: vi.fn(),
    onAudio: vi.fn(),
    onControl: vi.fn(),
    onError: vi.fn(),
    onClosed: vi.fn(),
  };
}
async function settle() {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}
async function connected() {
  const observer = events();
  const transport = new SimliTransport(observer);
  const opening = transport.connect(session, new AbortController().signal);
  await settle();
  expect(FakePeer.instances).toHaveLength(1);
  expect(FakeSocket.instances).toHaveLength(1);
  FakeSocket.instances[0].open();
  await opening;
  return { transport, observer, pc: FakePeer.instances[0], ws: FakeSocket.instances[0] };
}
beforeEach(() => {
  FakePeer.instances = [];
  FakeSocket.instances = [];
  vi.stubGlobal('RTCPeerConnection', FakePeer);
  vi.stubGlobal('WebSocket', FakeSocket);
  vi.stubGlobal('MediaStream', FakeStream);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('offers already collected candidates after the gathering window instead of discarding a usable connection', async () => {
  vi.useFakeTimers();
  vi.spyOn(FakePeer.prototype, 'createOffer').mockResolvedValue({
    type: 'offer',
    sdp: 'v=0\r\na=candidate:1 1 UDP 1 192.0.2.1 9000 typ host\r\n',
  });
  const transport = new SimliTransport(events());
  const opening = transport.connect(session, new AbortController().signal);
  FakePeer.instances[0].iceGatheringState = 'gathering';
  await settle();
  await vi.advanceTimersByTimeAsync(5000);
  expect(FakeSocket.instances).toHaveLength(1);
  FakeSocket.instances[0].open();
  await opening;
  expect(JSON.parse(FakeSocket.instances[0].send.mock.calls[0][0]).sdp).toContain('a=candidate:');
  transport.close();
  expect(vi.getTimerCount()).toBe(0);
});

it('fails gathering without candidates and reports only the fixed phase, without a signed URL', async () => {
  vi.useFakeTimers();
  const transport = new SimliTransport(events());
  const opening = transport.connect(session, new AbortController().signal);
  const rejected = expect(opening).rejects.toThrow('avatar_connect_failed');
  FakePeer.instances[0].iceGatheringState = 'gathering';
  await settle();
  await vi.advanceTimersByTimeAsync(5000);
  await rejected;
  expect(FakeSocket.instances).toHaveLength(0);
  expect(logger.warn).toHaveBeenCalledWith('avatar_connection_failed', {
    component: 'SimliTransport',
    phase: 'ice',
  });
  expect(JSON.stringify(vi.mocked(logger.warn).mock.calls)).not.toContain('test-token');
});

it('offers receive-only media to the fixed Compose v2 wire without a microphone', async () => {
  const { transport, pc, ws } = await connected();
  expect(pc.transceivers).toEqual([
    { kind: 'audio', direction: 'recvonly' },
    { kind: 'video', direction: 'recvonly' },
  ]);
  expect(pc.config.iceServers).toEqual(session.ice_servers);
  expect(ws.url).toBe(
    'wss://api.simli.ai/compose/webrtc/p2p?session_token=test-token&enableSFU=true'
  );
  expect(JSON.parse(ws.send.mock.calls[0][0])).toEqual({
    type: 'offer',
    sdp: pc.localDescription?.sdp,
  });
  ws.emit(JSON.stringify({ type: 'answer', sdp: 'v=0\r\na=answer' }));
  await settle();
  expect(pc.remoteDescription).toEqual({ type: 'answer', sdp: 'v=0\r\na=answer' });
  transport.close();
});
it('SKIP keeps the session open, PCM respects backpressure, and DONE closes once', async () => {
  const { transport, pc, ws } = await connected();
  const packet = new Uint8Array(6000);
  expect(transport.sendPcm(packet)).toBe(true);
  ws.bufferedAmount = 160001;
  expect(transport.sendPcm(packet)).toBe(false);
  transport.skip();
  expect(ws.send.mock.calls.map(call => call[0])).toContain('SKIP');
  expect(pc.close).not.toHaveBeenCalled();
  transport.close();
  transport.close();
  expect(ws.send.mock.calls.filter(call => call[0] === 'DONE')).toHaveLength(1);
  expect(pc.close).toHaveBeenCalledTimes(1);
});
it('owns only received Simli tracks and ignores controls/tracks from a closed epoch', async () => {
  const { transport, observer, pc, ws } = await connected();
  const track = new FakeTrack('audio');
  pc.ontrack?.({ track, streams: [] });
  expect(observer.onAudio).toHaveBeenCalledTimes(1);
  const lateTrack = pc.ontrack;
  const lateMessage = ws.onmessage;
  transport.close();
  expect(track.stop).toHaveBeenCalledTimes(1);
  lateTrack?.({ track: new FakeTrack('video'), streams: [] });
  lateMessage?.({ data: 'START' });
  expect(observer.onVideo).not.toHaveBeenCalled();
  expect(observer.onControl).not.toHaveBeenCalled();
  expect(observer.onClosed).toHaveBeenCalledTimes(1);
});
it('presents audio and video in the same stream instead of breaking their browser synchronization', async () => {
  const { transport, observer, pc } = await connected();
  const audio = new FakeTrack('audio');
  const video = new FakeTrack('video');
  pc.ontrack?.({ track: audio, streams: [] });
  pc.ontrack?.({ track: video, streams: [] });
  const stream = vi.mocked(observer.onVideo).mock.calls[0][0];
  expect(stream).toBe(vi.mocked(observer.onAudio).mock.calls[0][0]);
  expect(stream.getTracks()).toEqual([audio, video]);
  transport.close();
});

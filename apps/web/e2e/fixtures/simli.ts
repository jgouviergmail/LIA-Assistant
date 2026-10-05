/** Hermetic Compose peer: real loopback WebRTC, canvas/video and PCM/audio. */
import type { Page } from '@playwright/test';
import type { MockRoute } from './api-mock';
import encodedSamples from './audio-codecs.json';

const fixtureIceServers: RTCIceServer[] = process.env.SIMLI_TEST_ICE_URL
  ? [{ urls: process.env.SIMLI_TEST_ICE_URL }]
  : [];

declare global {
  interface Window {
    simliFixture: {
      answer(sdp: string, kind?: 'avatar' | 'native'): Promise<string>;
      pcm(bytes: number[], kind?: 'avatar' | 'native'): Promise<void>;
      close(kind?: 'avatar' | 'native'): void;
      nativeEvent(event: Record<string, unknown>): void;
      localStarts: number;
      decoded: Array<{ frames: number; rate: number }>;
      borrowedStops: number;
      captureFrames: number;
      capturePeak: number;
      renderedPeak: number;
      nativeDiagnostics(): Promise<unknown>;
    };
  }
}

export const avatarConfig = {
  available: true,
  enabled: true,
  connected: true,
  face_id: 'cace3ef7-a4c4-425d-a8cf-a5358eb0c427',
  connector_version: 'fixture-version',
  session_length_seconds: 3600,
  connect_timeout_seconds: 15,
};

export function avatarRoutes(starts: unknown[], releases: unknown[]): MockRoute[] {
  return [
    { url: '**/api/v1/avatars/config', json: avatarConfig },
    {
      url: '**/api/v1/avatars/sessions',
      method: 'POST',
      handler: async route => {
        starts.push(route.request().postDataJSON());
        await route.fulfill({
          json: {
            session_token: 'hermetic-simli',
            lease_id: crypto.randomUUID(),
            ice_servers: fixtureIceServers,
            max_session_seconds: 3600,
          },
        });
      },
    },
    { url: '**/api/v1/avatars/sessions/heartbeat', method: 'POST', status: 204 },
    {
      url: '**/api/v1/avatars/sessions/release',
      method: 'POST',
      handler: async route => {
        releases.push(route.request().postDataJSON());
        await route.fulfill({ json: { released: true } });
      },
    },
  ];
}

export async function installSimliPeer(page: Page) {
  await page.addInitScript(iceServers => {
    const NativePeer = RTCPeerConnection;
    const NativeContext = AudioContext;
    const contexts: AudioContext[] = [];
    window.AudioContext = class extends NativeContext {
      constructor(options?: AudioContextOptions) {
        super(options);
        contexts.push(this);
      }
    };
    const receivers: RTCPeerConnection[] = [];
    const rtcSteps: Array<{ step: string; state?: string; ms: number }> = [];
    const rtcBegan = performance.now();
    const NativeSocket = WebSocket;
    window.WebSocket = class extends NativeSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        rtcSteps.push({ step: 'socket-construct', ms: Math.round(performance.now() - rtcBegan) });
        super(url, protocols);
        if (!String(url).startsWith('wss://api.simli.ai/')) return;
        for (const name of ['open', 'error', 'close'])
          this.addEventListener(name, () =>
            rtcSteps.push({ step: `socket-${name}`, ms: Math.round(performance.now() - rtcBegan) })
          );
      }
    };
    const NativeWorklet = AudioWorkletNode;
    window.AudioWorkletNode = class extends NativeWorklet {
      constructor(context: BaseAudioContext, name: string, options?: AudioWorkletNodeOptions) {
        super(context, name, options);
        if (name !== 'lia-remote-pcm-capture') return;
        this.port.addEventListener('message', event => {
          if (!(event.data?.pcm instanceof ArrayBuffer)) return;
          window.simliFixture.captureFrames++;
          const samples = new DataView(event.data.pcm);
          for (let n = 0; n < samples.byteLength; n += 2)
            window.simliFixture.capturePeak = Math.max(
              window.simliFixture.capturePeak,
              Math.abs(samples.getInt16(n, true))
            );
        });
      }
    };
    type Peer = {
      peer: RTCPeerConnection;
      audio: AudioContext;
      destination: MediaStreamAudioDestinationNode;
      video: MediaStream | null;
      canvas: HTMLCanvasElement | null;
      timer: ReturnType<typeof setInterval> | null;
      due: number;
    };
    const peers = new Map<string, Peer>();
    let nativeChannel: RTCDataChannel | null = null;
    window.RTCPeerConnection = class extends NativePeer {
      constructor(config?: RTCConfiguration) {
        super(config);
        rtcSteps.push({ step: 'construct', ms: Math.round(performance.now() - rtcBegan) });
        this.addEventListener('icegatheringstatechange', () =>
          rtcSteps.push({
            step: 'ice',
            state: `${this.iceGatheringState}:${!!this.localDescription?.sdp}`,
            ms: Math.round(performance.now() - rtcBegan),
          })
        );
        receivers.push(this);
        if (config) return; // Simli owns its tracks; GPT-Live borrows native tracks.
        this.addEventListener('track', event => {
          const stop = event.track.stop.bind(event.track);
          event.track.stop = () => {
            window.simliFixture.borrowedStops++;
            stop();
          };
        });
      }
      // The DOM type keeps the legacy callback overload; the override must carry both.
      createOffer(options?: RTCOfferOptions): Promise<RTCSessionDescriptionInit>;
      createOffer(
        successCallback: RTCSessionDescriptionCallback,
        failureCallback: RTCPeerConnectionErrorCallback,
        options?: RTCOfferOptions
      ): Promise<void>;
      async createOffer(
        first?: RTCOfferOptions | RTCSessionDescriptionCallback,
        failure?: RTCPeerConnectionErrorCallback,
        options?: RTCOfferOptions
      ): Promise<RTCSessionDescriptionInit | void> {
        if (typeof first === 'function') {
          if (!failure) throw new TypeError('legacy createOffer needs both callbacks');
          return super.createOffer(first, failure, options);
        }
        try {
          const offer = await super.createOffer(first);
          rtcSteps.push({ step: 'offer', ms: Math.round(performance.now() - rtcBegan) });
          return offer;
        } catch (error) {
          rtcSteps.push({
            step: 'offer-error',
            state: (error as DOMException).name,
            ms: Math.round(performance.now() - rtcBegan),
          });
          throw error;
        }
      }
      async setLocalDescription(description?: RTCLocalSessionDescriptionInit) {
        rtcSteps.push({ step: 'local-begin', ms: Math.round(performance.now() - rtcBegan) });
        try {
          await super.setLocalDescription(description);
          rtcSteps.push({ step: 'local-end', ms: Math.round(performance.now() - rtcBegan) });
        } catch (error) {
          rtcSteps.push({
            step: 'local-error',
            state: (error as DOMException).name,
            ms: Math.round(performance.now() - rtcBegan),
          });
          throw error;
        }
      }
    };
    const originalStart = AudioBufferSourceNode.prototype.start;
    const originalSamples = AnalyserNode.prototype.getFloatTimeDomainData;
    AnalyserNode.prototype.getFloatTimeDomainData = function (array) {
      originalSamples.call(this, array);
      if ([...peers.values()].some(peer => peer.audio === this.context)) return;
      for (const sample of array)
        window.simliFixture.renderedPeak = Math.max(
          window.simliFixture.renderedPeak,
          Math.abs(sample)
        );
    };
    const originalDecode = AudioContext.prototype.decodeAudioData;
    AudioContext.prototype.decodeAudioData = function (data, success, failure) {
      return originalDecode.call(this, data, success, failure).then(buffer => {
        window.simliFixture.decoded.push({ frames: buffer.length, rate: buffer.sampleRate });
        return buffer;
      });
    };
    AudioBufferSourceNode.prototype.start = function (...args) {
      // A silent iOS unlock buffer is not a second spoken output.
      if (
        this.buffer &&
        this.buffer.getChannelData(0).some(sample => sample !== 0) &&
        ![...peers.values()].some(peer => peer.audio === this.context)
      )
        window.simliFixture.localStarts++;
      return originalStart.apply(this, args);
    };
    const unlock = () => {
      for (const peer of peers.values()) void peer.audio.resume().catch(() => {});
    };
    document.addEventListener('click', unlock);
    document.addEventListener('keydown', unlock);
    window.simliFixture = {
      localStarts: 0,
      decoded: [],
      borrowedStops: 0,
      captureFrames: 0,
      capturePeak: 0,
      renderedPeak: 0,
      async nativeDiagnostics() {
        const entry = peers.get('native') ?? peers.get('avatar');
        const stats = [];
        for (const peer of [entry?.peer, ...receivers]) {
          if (!peer) continue;
          const result = await peer.getStats();
          for (const item of result.values()) {
            if (!['inbound-rtp', 'outbound-rtp', 'media-source'].includes(item.type)) continue;
            stats.push({
              type: item.type,
              kind: item.kind,
              bytesSent: item.bytesSent,
              bytesReceived: item.bytesReceived,
              audioLevel: item.audioLevel,
              totalAudioEnergy: item.totalAudioEnergy,
            });
          }
        }
        const video = document.querySelector('video');
        return {
          audioState: entry?.audio.state,
          time: entry?.audio.currentTime,
          stats,
          rtcSteps,
          contexts: contexts.map(context => ({ state: context.state, rate: context.sampleRate })),
          video: video
            ? {
                paused: video.paused,
                readyState: video.readyState,
                time: video.currentTime,
                width: video.videoWidth,
              }
            : null,
          connections: [entry?.peer, ...receivers]
            .filter((peer): peer is RTCPeerConnection => !!peer)
            .map(peer => ({
              state: peer.connectionState,
              ice: peer.iceConnectionState,
              candidates: [peer.localDescription?.sdp, peer.remoteDescription?.sdp].map(sdp =>
                [...(sdp ?? '').matchAll(/^a=candidate:.*$/gm)].map(match => ({
                  mdns: match[0].includes('.local'),
                  transport: match[0].split(' ')[2],
                  type: match[0].split(' ')[7],
                }))
              ),
            })),
        };
      },
      nativeEvent(event) {
        nativeChannel?.send(JSON.stringify(event));
      },
      async answer(sdp, kind = 'avatar') {
        const peer = new NativePeer({ iceServers });
        const audio = new AudioContext();
        const destination = audio.createMediaStreamDestination();
        const entry: Peer = {
          peer,
          audio,
          destination,
          video: null,
          canvas: null,
          timer: null,
          due: 0,
        };
        peers.set(kind, entry);
        if (kind === 'native')
          peer.ondatachannel = event => {
            nativeChannel = event.channel;
            event.channel.onopen = () =>
              event.channel.send(JSON.stringify({ type: 'session.started' }));
            event.channel.onmessage = message => {
              if (
                (JSON.parse(String(message.data)) as Record<string, unknown>).type ===
                'session.close'
              ) {
                event.channel.send(
                  JSON.stringify({ type: 'session.closed', reason: 'close_requested' })
                );
              }
            };
          };
        const canvas = document.createElement('canvas');
        canvas.width = 160;
        canvas.height = 160;
        canvas.style.cssText =
          'position:fixed;left:0;top:0;width:1px;height:1px;pointer-events:none';
        const context = canvas.getContext('2d');
        let frame = 0;
        const draw = () => {
          if (!context) return;
          context.fillStyle = frame++ % 2 ? '#204060' : '#305070';
          context.fillRect(0, 0, 160, 160);
          context.fillStyle = '#ffffff';
          context.fillText('Synthetic avatar', 15, 80);
        };
        if (kind === 'avatar') {
          document.body.appendChild(canvas);
          entry.canvas = canvas;
          draw();
          entry.timer = setInterval(draw, 50);
          entry.video = canvas.captureStream(20);
        }
        for (const track of destination.stream.getAudioTracks())
          peer.addTrack(track, destination.stream);
        for (const track of entry.video?.getVideoTracks() ?? []) peer.addTrack(track, entry.video!);
        await peer.setRemoteDescription({ type: 'offer', sdp });
        await peer.setLocalDescription(await peer.createAnswer());
        if (peer.iceGatheringState !== 'complete')
          await new Promise<void>(resolve => {
            const current = peer;
            const onChange = () => {
              if (current?.iceGatheringState !== 'complete') return;
              current.removeEventListener('icegatheringstatechange', onChange);
              resolve();
            };
            current?.addEventListener('icegatheringstatechange', onChange);
          });
        return peer.localDescription?.sdp ?? '';
      },
      async pcm(bytes, kind = 'avatar') {
        const entry = peers.get(kind);
        if (!entry) return;
        const { audio, destination } = entry;
        await audio.resume();
        const buffer = audio.createBuffer(1, bytes.length / 2, 16000);
        const channel = buffer.getChannelData(0);
        const view = new DataView(new Uint8Array(bytes).buffer);
        for (let n = 0; n < channel.length; n++) channel[n] = view.getInt16(n * 2, true) / 32768;
        const source = audio.createBufferSource();
        source.buffer = buffer;
        source.connect(destination);
        entry.due = Math.max(audio.currentTime + 0.01, entry.due);
        source.start(entry.due);
        entry.due += buffer.duration;
      },
      close(kind = 'avatar') {
        const entry = peers.get(kind);
        if (!entry) return;
        peers.delete(kind);
        if (entry.timer) clearInterval(entry.timer);
        entry.peer.close();
        entry.video?.getTracks().forEach(track => track.stop());
        entry.destination.stream.getTracks().forEach(track => track.stop());
        entry.canvas?.remove();
        void entry.audio.close().catch(() => {});
      },
    };
  }, fixtureIceServers);
  const frames: (string | Buffer)[] = [];
  await page.routeWebSocket('wss://api.simli.ai/compose/webrtc/p2p*', ws => {
    ws.onMessage(async message => {
      frames.push(message);
      if (typeof message !== 'string') {
        await page.evaluate(bytes => window.simliFixture.pcm(bytes), [...message]);
        return;
      }
      if (message === 'SKIP') return;
      if (message === 'DONE') {
        await page.evaluate(() => window.simliFixture.close());
        return;
      }
      const offer = JSON.parse(message) as { type: string; sdp: string };
      const sdp = await page.evaluate(sdp => window.simliFixture.answer(sdp), offer.sdp);
      ws.send(JSON.stringify({ type: 'answer', sdp }));
      ws.send('START');
      ws.send('ACK');
    });
  });
  return frames;
}
export function encodedSpokenSample(format: 'mp3' | 'mp4'): string {
  return encodedSamples[format];
}

export function spokenWave(): string {
  const rate = 24000;
  const frames = rate / 2;
  const wav = Buffer.alloc(44 + frames * 2);
  wav.write('RIFF');
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(rate, 24);
  wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write('data', 36);
  wav.writeUInt32LE(frames * 2, 40);
  for (let n = 0; n < frames; n++)
    wav.writeInt16LE(Math.round(1000 * Math.sin((2 * Math.PI * 700 * n) / rate)), 44 + n * 2);
  return wav.toString('base64');
}

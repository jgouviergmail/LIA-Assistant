import type { AvatarSession } from './types';
import type { SimliControl } from './simli-protocol';
import { parseSimliSignal } from './simli-protocol';
import { AVATAR_PCM_MAX_BACKLOG_BYTES, AVATAR_PCM_PACKET_BYTES } from '../voice-output/types';
import { logger } from '@/lib/logger';

const ICE_TIMEOUT_MS = 5000;
const TERMINAL_CONTROLS: readonly SimliControl[] = ['STOP', 'RATE', 'ERROR', 'CLOSING'];

function waitForIce(pc: RTCPeerConnection, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  if (pc.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      // Some TURN/STUN servers remain unreachable while host/relay candidates
      // are already usable. Bound gathering, then offer what the browser has;
      // this wire does not support separately sending trickled candidates.
      const usable = /(?:^|\r?\n)a=candidate:/.test(pc.localDescription?.sdp ?? '');
      finish(usable ? undefined : new Error('avatar_ice_timeout'));
    }, ICE_TIMEOUT_MS);
    function finish(error?: Error) {
      clearTimeout(timer);
      pc.removeEventListener('icegatheringstatechange', check);
      signal.removeEventListener('abort', abort);
      if (error) reject(error);
      else resolve();
    }
    function check() {
      if (pc.iceGatheringState === 'complete') finish();
    }
    function abort() {
      finish(new DOMException('Aborted', 'AbortError'));
    }
    pc.addEventListener('icegatheringstatechange', check);
    signal.addEventListener('abort', abort, { once: true });
  });
}

export interface SimliTransportEvents {
  onVideo(stream: MediaStream): void;
  onAudio(stream: MediaStream): void;
  onControl(control: SimliControl): void;
  onError(code: string): void;
  onClosed(): void;
}

export class SimliTransport {
  private pc: RTCPeerConnection | null = null;
  private ws: WebSocket | null = null;
  private epoch = 0;
  private controller: AbortController | null = null;
  private removeAbort: (() => void) | null = null;
  private tracks = new Set<MediaStreamTrack>();
  private presentation: MediaStream | null = null;
  constructor(readonly events: SimliTransportEvents) {}

  async connect(session: AvatarSession, signal: AbortSignal): Promise<void> {
    if (this.pc) throw new Error('avatar_transport_already_open');
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const epoch = ++this.epoch;
    const controller = new AbortController();
    this.controller = controller;
    const abort = () => this.close();
    signal.addEventListener('abort', abort, { once: true });
    this.removeAbort = () => signal.removeEventListener('abort', abort);
    let phase = 'offer';
    const at = (next: string) => {
      phase = next;
      logger.debug('avatar_connection_phase', { component: 'SimliTransport', phase });
    };
    try {
      const pc = new RTCPeerConnection({ iceServers: session.ice_servers });
      this.pc = pc;
      this.presentation = new MediaStream();
      pc.addTransceiver('audio', { direction: 'recvonly' });
      pc.addTransceiver('video', { direction: 'recvonly' });
      this.bindPeer(pc, epoch);
      const offer = await pc.createOffer();
      this.assertCurrent(epoch);
      at('local_description');
      await pc.setLocalDescription(offer);
      at('ice');
      await waitForIce(pc, controller.signal);
      this.assertCurrent(epoch);
      at('socket');
      await this.openSocket(
        session.session_token,
        pc.localDescription?.sdp,
        epoch,
        controller.signal
      );
    } catch {
      const cancelled = signal.aborted || controller.signal.aborted;
      if (!cancelled)
        logger.warn('avatar_connection_failed', { component: 'SimliTransport', phase });
      if (epoch === this.epoch) this.close();
      // Browser exceptions can contain the signed WebSocket URL. Never retain
      // their text/cause in logs, error messages, diagnostics or application state.
      throw new Error(cancelled ? 'avatar_connect_cancelled' : 'avatar_connect_failed');
    }
  }

  private assertCurrent(epoch: number): void {
    if (epoch !== this.epoch || !this.pc) throw new DOMException('Aborted', 'AbortError');
  }

  private bindPeer(pc: RTCPeerConnection, epoch: number): void {
    pc.ontrack = event => {
      if (epoch !== this.epoch) return;
      this.tracks.add(event.track);
      const stream = this.presentation;
      if (!stream) return;
      stream.addTrack(event.track);
      try {
        if (event.track.kind === 'audio') this.events.onAudio(stream);
        else if (event.track.kind === 'video') this.events.onVideo(stream);
      } catch {
        this.fail('avatar_media_failed');
      }
    };
    pc.onconnectionstatechange = () => {
      if (epoch !== this.epoch) return;
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed')
        this.fail('avatar_rtc_failed');
    };
  }

  private openSocket(
    token: string,
    sdp: string | undefined,
    epoch: number,
    signal: AbortSignal
  ): Promise<void> {
    if (!token || token.length > 8192 || !sdp) throw new Error('avatar_bad_credential');
    const ws = new WebSocket(
      `wss://api.simli.ai/compose/webrtc/p2p?session_token=${encodeURIComponent(token)}&enableSFU=true`
    );
    this.ws = ws;
    ws.binaryType = 'arraybuffer';
    return new Promise((resolve, reject) => {
      const abort = () => reject(new Error('avatar_connect_cancelled'));
      signal.addEventListener('abort', abort, { once: true });
      const settled = () => signal.removeEventListener('abort', abort);
      ws.onopen = () => {
        if (epoch !== this.epoch) {
          settled();
          reject(new Error('avatar_connect_cancelled'));
          return;
        }
        try {
          ws.send(JSON.stringify({ type: 'offer', sdp }));
          settled();
          resolve();
        } catch {
          settled();
          reject(new Error('avatar_signaling_failed'));
        }
      };
      ws.onmessage = event => {
        if (epoch === this.epoch) void this.receive(event.data, epoch);
      };
      ws.onerror = () => {
        settled();
        reject(new Error('avatar_socket_failed'));
        if (epoch === this.epoch) this.fail('avatar_socket_failed');
      };
      ws.onclose = () => {
        settled();
        reject(new Error('avatar_socket_closed'));
        if (epoch === this.epoch) this.close();
      };
    });
  }

  private async receive(data: unknown, epoch: number): Promise<void> {
    const signal = parseSimliSignal(data);
    if (signal.kind === 'control') {
      this.events.onControl(signal.control);
      if (epoch === this.epoch && TERMINAL_CONTROLS.includes(signal.control))
        this.fail('avatar_provider_closed');
      return;
    }
    if (signal.kind !== 'answer') return;
    try {
      await this.pc?.setRemoteDescription({ type: 'answer', sdp: signal.sdp });
    } catch {
      if (epoch === this.epoch) this.fail('avatar_bad_answer');
    }
  }

  sendPcm(packet: Uint8Array): boolean {
    const ws = this.ws;
    if (!packet.length || packet.length % 2 || packet.length > AVATAR_PCM_PACKET_BYTES)
      throw new Error('avatar_bad_pcm');
    if (
      !ws ||
      ws.readyState !== 1 ||
      ws.bufferedAmount + packet.length > AVATAR_PCM_MAX_BACKLOG_BYTES
    )
      return false;
    // Own the wire buffer; never pass a possible SharedArrayBuffer to WebSocket.
    ws.send(packet.slice().buffer);
    return true;
  }

  skip(): void {
    try {
      if (this.ws?.readyState === 1) this.ws.send('SKIP');
    } catch {
      this.fail('avatar_send_failed');
    }
  }

  private fail(code: string): void {
    this.events.onError(code);
    this.close();
  }

  close(): void {
    if (!this.controller) return;
    this.epoch++;
    const controller = this.controller;
    this.controller = null;
    controller.abort();
    this.removeAbort?.();
    this.removeAbort = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      try {
        if (ws.readyState === 1) ws.send('DONE');
      } catch {
        /* Close still owns cleanup. */
      }
      ws.close();
    }
    if (this.pc) {
      this.pc.ontrack = this.pc.onconnectionstatechange = null;
      this.pc.close();
      this.pc = null;
    }
    for (const track of this.tracks) track.stop();
    this.tracks.clear();
    this.presentation = null;
    this.events.onClosed();
  }
}

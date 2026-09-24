/**
 * LiveSessionController — one session, from the mint to the closing card
 * (ADR-299, spec A6 and A7).
 *
 * Owns the transport, the microphone, the player and the delegation bridge;
 * publishes everything the banner and the eyes read into `useLiveStore`; and
 * speaks to the chat through the bindings it is handed (the chat's own
 * `sendMessage` is the door — never a request of this controller's own).
 *
 * A DIRECT session (ADR-300 wave 4) builds no bridge: every function call the
 * provider hands over is a lookup, posted to the API's tool door on the
 * session and answered on the same call id — the phone's own line, in the
 * browser. Its exchanges are voice-only, archived like any other.
 *
 * It is a plain class so the orchestration is tested without React and reads
 * as a sequence of small steps; `useLiveSession` is the thin hook around it.
 *
 * Three facts measured on 2026-09-18 shape it: a used credential cannot
 * reconnect (every reconnection asks the API for a fresh one), a text pushed
 * after a tool call is spoken (a late delegation answer is delivered that
 * way), and the provider announces its disconnection (`goAway`) early enough
 * to reconnect before it.
 *
 * The one-owner-of-the-microphone rule (ADR-258) is enforced by the CALLER,
 * which refuses to start while a meeting records; this controller pauses
 * nothing.
 */
import { parseActivity } from '@/components/eyes/activity';
import { inferToneFromContent, REGISTER_EXPRESSIONS, toneAmplitude } from '@/components/eyes/tone';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { getApiErrorCode } from '@/lib/api-error';
import { LIVE_GO_AWAY_MARGIN_MS, LIVE_IDLE_COUNTDOWN_MS } from '@/lib/constants';
import type { Message } from '@/types/chat';
import { meterCost } from '@/lib/live/meter';
import { useLiveStore } from '@/stores/liveStore';

import { ActivityClock } from './activity-clock';
import { DelegationBridge, type ReadAnswer } from './delegation';
import type { MicCapture, MicCaptureOptions } from './mic-capture';
import type { PcmPlayerDiagnostics } from './pcm-player';
import {
  LIVE_END_DETAIL_MAX_CHARS,
  closeDecision,
  closeDetail,
  isSessionOpen,
} from './session-machine';
import type { LiveTransport } from './transport';
import type {
  LiveConfigResponse,
  LiveCredential,
  LiveEndResponse,
  LiveDelegation,
  LiveExtendResponse,
  LiveInteractionStatus,
  LiveOfferResponse,
  LiveOutcome,
  LiveSessionMode,
  LiveSessionStart,
  LiveToolCallResponse,
  LiveTranscriptRole,
  LiveTurnResponse,
} from './types';

/** What a delegated turn tells the chat beside the request. */
export interface LiveSpokenMeta {
  live_session_id: string;
  spoken_text: string | null;
}

/** The chat's doors, as the page hands them over. */
export interface LiveChatBindings {
  sendMessage: (content: string, meta: LiveSpokenMeta) => Promise<void>;
  /** The chat's own Stop: cancels the running turn (ADR-117). */
  stop: () => Promise<void>;
  appendMessage: (message: Message) => void;
  /** The last answer as the thread holds it once the stream's final state is committed. */
  readAnswer: () => Promise<ReadAnswer>;
}

/** The player's surface, so a test can hand a fake. */
export interface LivePlayer {
  readonly isSpeaking: boolean;
  warmup(): Promise<void>;
  enqueue(pcm16: ArrayBuffer, sampleRate: number): void;
  flush(): void;
  dispose(): void;
  onSpeakingChange(listener: (speaking: boolean) => void): void;
  diagnostics?(): PcmPlayerDiagnostics | null;
}

export interface LiveApi {
  get<T>(url: string): Promise<T>;
  post<T>(url: string, body?: unknown): Promise<T>;
}

export interface LiveControllerDeps {
  api: LiveApi;
  createTransport: (provider: string, audioTransport?: 'websocket' | 'webrtc') => LiveTransport;
  createPlayer: () => LivePlayer;
  startMic: (options: MicCaptureOptions) => Promise<MicCapture>;
  /** Whether this browser can hold a session — asked before anything is minted. */
  isSupported: () => boolean;
  chat: LiveChatBindings;
}

interface TurnBuffer {
  user: string;
  assistant: string;
  startedAt: number;
  /** The turn handed a request to LIA: its rows belong to the chat turn. */
  delegated: boolean;
}

const LIVE_TURN_TYPE = 'live_turn';
const LIVE_SUMMARY_TYPE = 'live_session_summary';
/** Leave the browser time to complete a WebSocket handshake before a token's opening deadline. */
const LIVE_CONNECT_MARGIN_MS = 15_000;

/** The API no longer holds this session (404): superseded, or past its cap and grace. */
function isGone(error: unknown): boolean {
  return (
    typeof error === 'object' && error !== null && (error as { status?: unknown }).status === 404
  );
}

/** What `POST /live/sessions/{id}/turns` takes: the two bounded texts and the exchange's span. */
interface TurnBody {
  user_text: string | null;
  assistant_text: string | null;
  started_at: string;
  ended_at: string;
}

/** The exchange as a turn body, or null when nothing was said on either side. */
export function turnBody(turn: TurnBuffer, maxChars: number): TurnBody | null {
  const user_text = turn.user.trim().slice(0, maxChars) || null;
  const assistant_text = turn.assistant.trim().slice(0, maxChars) || null;
  if (!user_text && !assistant_text) return null;
  return {
    user_text,
    assistant_text,
    started_at: new Date(turn.startedAt || Date.now()).toISOString(),
    ended_at: new Date().toISOString(),
  };
}

function freshTurn(): TurnBuffer {
  return { user: '', assistant: '', startedAt: 0, delegated: false };
}

export class LiveSessionController {
  private readonly store = useLiveStore;
  /** The chat's doors, replaced by the hook on every render so a delegated turn reaches the CURRENT chat. */
  private chat: LiveChatBindings;
  private transport: LiveTransport | null = null;
  private player: LivePlayer | null = null;
  private mic: MicCapture | null = null;
  private bridge: DelegationBridge | null = null;
  private clock: ActivityClock | null = null;
  private session: LiveSessionStart | null = null;
  private config: LiveConfigResponse | null = null;
  private handle: string | null = null;
  /** The provider's own conversation id, when its wire named one (ElevenLabs). */
  private providerConversationId: string | null = null;
  private attempts = 0;
  /** Bumped at every connection; events of an older socket are ignored. */
  private generation = 0;
  private turn: TurnBuffer = freshTurn();
  /** The next caption opens a new line (a turn just completed). */
  private captionBreak = false;
  private timers: Partial<
    Record<'hidden' | 'expiry' | 'extension' | 'goAway' | 'budget', ReturnType<typeof setTimeout>>
  > = {};
  private ending = false;
  private awaitingMicrophone = false;
  private pageIsHidden = false;

  constructor(private readonly deps: LiveControllerDeps) {
    this.chat = deps.chat;
  }

  // -- public surface --------------------------------------------------------

  /** Point at the chat as the page renders it now (the hook calls this in an effect). */
  setChat(chat: LiveChatBindings): void {
    this.chat = chat;
  }

  /** Open a session: the click that calls this is the user gesture the player needs. */
  async start(mode: LiveSessionMode = 'delegated'): Promise<void> {
    const status = this.store.getState().status;
    if (status !== 'idle' && status !== 'ended') return;
    if (!this.deps.isSupported()) {
      // No request leaves: nothing is claimed, minted or counted for a
      // browser that could not open the socket or the microphone anyway.
      this.store.getState().finish('error', 'unsupported_browser');
      return;
    }
    this.ending = false;
    this.turn = freshTurn();
    this.handle = null;
    this.providerConversationId = null;
    this.attempts = 0;
    const player = this.deps.createPlayer();
    this.player = player;
    let session: LiveSessionStart;
    try {
      await player.warmup();
      this.config = await this.deps.api.get<LiveConfigResponse>('/live/config');
      this.store.getState().setExtensionMinutes(this.config.extension_minutes);
      session = await this.deps.api.post<LiveSessionStart>('/live/sessions', {
        mode,
        audio_transport: /iPhone|iPad|iPod/.test(navigator.userAgent) ? 'webrtc' : 'websocket',
      });
      this.session = session;
      this.store.getState().begin(session.session_id, session.mode);
      this.store.getState().apply('minted');
      this.store.getState().setRates(session.rates, session.session_budget_eur);
      this.store.getState().setVendorBilled(session.capabilities.vendor_billed);
      this.bindPlayer(player);
      // A direct session delegates nothing: no bridge, the chat's doors unused.
      this.bridge = session.mode === 'direct' ? null : this.buildBridge(session);
      this.transport = this.deps.createTransport(session.provider, session.audio_transport);
      if (this.transport.audio.ownership === 'managed') {
        player.dispose();
        this.player = null;
      }
    } catch (error) {
      // Before the mint nothing exists server-side; after it, the record is
      // claimed and must be closed — with the reason named.
      if (this.session) await this.end('error', getApiErrorCode(error) ?? String(error));
      else this.failStart(error);
      return;
    }
    await this.establishInitialConnection(session);
  }

  /** Prepare the provider's audio, then open its first credentialed connection. */
  private async establishInitialConnection(session: LiveSessionStart): Promise<void> {
    const transport = this.transport;
    if (!transport) return;
    // The microphone BEFORE the connection: a native transport carries the
    // track in its offer, and a refused microphone must open no socket.
    if (transport.audio.ownership !== 'managed' && !(await this.openMicrophoneAfterPrompt())) {
      return;
    }
    try {
      this.awaitingMicrophone = transport.audio.ownership === 'managed';
      await this.connect(await this.firstCredential(session));
      this.awaitingMicrophone = false;
    } catch (error) {
      this.awaitingMicrophone = false;
      // Minted and claimed server-side: close the books, name the reason.
      const denied =
        error instanceof Error &&
        (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError');
      await this.end(denied ? 'mic_denied' : 'error', getApiErrorCode(error) ?? String(error));
      return;
    }
    this.armExpiry(session.expires_at, 0);
  }

  /**
   * Prolong the session on the person's explicit word (unlimited, each
   * explicit). Resolves false when the API refused — the session then ends at
   * its cap as planned.
   */
  async extend(): Promise<boolean> {
    const session = this.session;
    if (!session || this.ending) return false;
    this.store.getState().offerExtension(false);
    let extended: LiveExtendResponse;
    try {
      extended = await this.deps.api.post<LiveExtendResponse>(
        `/live/sessions/${session.session_id}/extend`,
        {}
      );
    } catch (error) {
      if (isGone(error)) void this.end('superseded');
      return false;
    }
    this.armExpiry(extended.expires_at, extended.extensions);
    // Measured 2026-09-19: the provider closes an open connection at its
    // credential's expiry — the fresh credential is ridden at once, on the
    // resumption handle, rather than waiting for the cut.
    if (extended.credential) await this.reconnect(extended.credential);
    return true;
  }

  /** The person let the dialog go: the session ends at its cap. */
  declineExtension(): void {
    this.store.getState().offerExtension(false);
  }

  /** Close the session's books: everything released, the card appended. */
  /**
   * End the session: close the wire, the microphone and the player, archive
   * the turn, close the books. `error` is the coded reason the store shows
   * (`live.error.*`); `detail` is the technical word — a provider's close
   * code and reason — LOGGED by the API and never shown, because an outcome
   * alone (« provider_closed ») left a session that died in five seconds
   * unexplained (measured 2026-09-19).
   */
  async end(
    outcome: LiveOutcome = 'ended',
    error: string | null = null,
    detail: string | null = null
  ): Promise<void> {
    if (this.ending) return;
    const session = this.session;
    if (!session) return;
    this.ending = true;
    this.store.getState().apply('end');
    this.clearTimers();
    this.clock?.stop();
    this.generation += 1;
    await this.transport?.close().catch(() => undefined);
    // A microphone that refuses to close must not keep the books open.
    await this.mic?.stop().catch(() => undefined);
    const audioDiagnostics = this.player?.diagnostics?.() ?? null;
    this.player?.dispose();
    await this.archiveTurn();
    await this.closeBooks(session, outcome, detail ?? error, audioDiagnostics ?? null);
    this.store.getState().finish(outcome, error, detail);
    this.release();
  }

  toggleMute(): void {
    this.setMuted(!this.store.getState().muted);
  }

  /** The page went hidden (or came back): a hidden page past the grace ends the session. */
  pageHidden(hidden: boolean): void {
    this.pageIsHidden = hidden;
    this.clearTimer('hidden');
    // iOS may mark the page hidden while its system microphone permission
    // sheet is open. The grace starts after that sheet has returned a stream.
    if (!hidden || !this.config || this.awaitingMicrophone) return;
    this.timers.hidden = setTimeout(() => {
      if (isSessionOpen(this.store.getState().status)) void this.end('hidden');
    }, this.config.hidden_grace_seconds * 1000);
  }

  // -- start ------------------------------------------------------------------

  private failStart(error: unknown): void {
    const code = getApiErrorCode(error);
    const message = error instanceof Error ? error.message : String(error);
    this.store.getState().finish('error', code ?? message);
    this.generation += 1;
    void this.transport?.close().catch(() => undefined);
    this.player?.dispose();
    this.release();
  }

  /** A system permission sheet is part of opening the mic, not a hidden live session. */
  private async openMicrophoneAfterPrompt(): Promise<boolean> {
    this.awaitingMicrophone = true;
    const micReady = await this.openMicrophone();
    this.awaitingMicrophone = false;
    if (!micReady) return false;
    if (this.ending || !this.session) {
      await this.mic?.stop().catch(() => undefined);
      this.mic = null;
      return false;
    }
    if (this.pageIsHidden) this.pageHidden(true);
    return true;
  }

  /** Refresh a credential whose opening window was spent on the permission sheet. */
  private async firstCredential(session: LiveSessionStart): Promise<LiveCredential> {
    if (Date.now() + LIVE_CONNECT_MARGIN_MS < Date.parse(session.connect_deadline_at)) {
      return session;
    }
    return this.deps.api.post<LiveCredential>(
      `/live/sessions/${session.session_id}/credential`,
      {}
    );
  }

  /** Open the microphone as the transport wants it; false when the person refused it. */
  private async openMicrophone(): Promise<boolean> {
    const audio = this.transport?.audio;
    if (!audio) return false;
    try {
      this.mic = await this.deps.startMic({
        sampleRate: audio.inputRate,
        chunkSamples: Math.round((audio.inputRate * audio.chunkMs) / 1000),
        pcm: audio.ownership === 'pcm',
        onChunk: pcm => this.transport?.sendAudio(pcm),
      });
      return true;
    } catch (error) {
      const detail = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
      const denied =
        error instanceof Error &&
        (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError');
      await this.end(denied ? 'mic_denied' : 'error', null, detail);
      return false;
    }
  }

  private bindPlayer(player: LivePlayer): void {
    player.onSpeakingChange(speaking => this.setSpeaking(speaking));
  }

  /** The provider's voice started or stopped — from the player or a native transport. */
  private setSpeaking(speaking: boolean): void {
    const state = this.store.getState();
    if (speaking) {
      state.setVoiceState('speaking');
      this.clock?.hold('speaking');
    } else {
      if (state.voiceState === 'speaking') state.setVoiceState('idle');
      this.clock?.release('speaking');
    }
  }

  private buildBridge(session: LiveSessionStart): DelegationBridge {
    return new DelegationBridge({
      send: (request, spokenText) =>
        this.chat.sendMessage(request, {
          live_session_id: session.session_id,
          spoken_text: spokenText,
        }),
      stop: () => this.chat.stop(),
      readAnswer: () => this.chat.readAnswer(),
      lines: {
        timed_out: this.config?.delegation_lines.timed_out ?? '',
        result_cut: this.config?.delegation_lines.result_cut ?? '',
        superseded: this.config?.delegation_lines.superseded ?? '',
        empty_request: this.config?.delegation_lines.empty_request ?? '',
        failed: this.config?.delegation_lines.failed,
      },
      superseded: id => {
        // Closed towards the voice without a word: the newer request answers.
        if (this.transport?.isOpen) {
          this.transport.answerDelegation(
            id,
            this.config?.delegation_lines.superseded ?? '',
            'silent'
          );
        }
      },
      toneLines: this.config?.tone_lines ?? {},
      timeoutMs: session.delegation_timeout_seconds * 1000,
      resultMaxTokens: session.delegation_result_max_tokens,
      delivery: session.preferences.result_delivery === 'when_idle' ? 'when_idle' : 'now',
      late: result => {
        if (this.transport?.isOpen) this.transport.sendText(result);
      },
      idle: () => {
        // A turn that outlived its wait ends here, long after the tool
        // response went out: the banner must stop saying LIA is working.
        const state = this.store.getState();
        state.setDelegating(false);
        if (state.voiceState === 'processing') state.setVoiceState('idle');
        this.clock?.release('delegating');
      },
    });
  }

  private setMuted(muted: boolean): void {
    this.mic?.mute(muted);
    // The provider is told its own way (activity markers, a stream end).
    this.transport?.setInputActive(!muted);
    this.store.getState().setMuted(muted);
  }

  // -- connection -------------------------------------------------------------

  private async connect(credential: LiveCredential): Promise<void> {
    const transport = this.transport;
    if (!transport) return;
    const session = this.session;
    if (!session) return;
    const generation = ++this.generation;
    const fresh = (): boolean => generation === this.generation && !this.ending;
    await transport.connect(
      {
        credential: credential.credential,
        setup: credential.setup,
        toolNames: session.tool_names,
        resumptionHandle: this.handle,
        capabilities: session.capabilities,
        microphone: transport.audio.ownership === 'native' ? (this.mic?.stream ?? null) : null,
        // An offer connection: the SDP is exchanged by the API on the person's
        // key, once per credential (the nonce is consumed server-side).
        exchangeOffer:
          credential.connection === 'offer'
            ? (nonce, sdp) =>
                this.deps.api
                  .post<LiveOfferResponse>(`/live/sessions/${session.session_id}/offer`, {
                    credential: nonce,
                    sdp,
                  })
                  .then(answer => answer.sdp)
            : undefined,
      },
      {
        onReady: () => {
          if (!fresh()) return;
          this.attempts = 0;
          this.store.getState().apply('setup_complete');
          this.store.getState().setTimeLeft(null);
          this.store.getState().markLive(Date.now());
          this.startClock();
          this.startBudgetClock();
        },
        onUsage: report => {
          if (!fresh()) return;
          this.store.getState().reportUsage(report);
          this.checkBudget();
        },
        onAudio: pcm => {
          if (!fresh()) return;
          this.player?.enqueue(pcm, transport.audio.outputRate);
        },
        onSpeakingChange: speaking => {
          if (fresh()) this.setSpeaking(speaking);
        },
        onInteractionStatus: status => {
          if (fresh()) this.onInteractionStatus(status);
        },
        onTranscript: (role, text) => {
          if (fresh()) this.onTranscript(role, text);
        },
        onTurnComplete: () => {
          if (fresh()) this.onTurnComplete();
        },
        onInterrupted: () => {
          if (!fresh()) return;
          this.player?.flush();
          this.store.getState().setVoiceState('recording');
        },
        onDelegation: delegations => (fresh() ? this.onDelegation(delegations) : undefined),
        onDelegationCancelled: ids => {
          if (fresh()) this.bridge?.cancel(ids);
        },
        onResumption: handle => {
          // A stale socket's late update would point the next reconnection at
          // an older point of the conversation.
          if (fresh()) this.handle = handle;
        },
        onProviderConversation: conversationId => {
          if (fresh()) this.providerConversationId = conversationId;
        },
        onGoAway: timeLeftMs => {
          if (fresh()) this.onGoAway(timeLeftMs);
        },
        onClosed: (code, reason) => {
          if (fresh()) this.onClosed(code, reason);
        },
        onError: () => undefined,
      }
    );
  }

  private onGoAway(timeLeftMs: number): void {
    this.store.getState().setTimeLeft(timeLeftMs);
    this.clearTimer('goAway');
    this.timers.goAway = setTimeout(
      () => void this.reconnect(),
      Math.max(0, timeLeftMs - LIVE_GO_AWAY_MARGIN_MS)
    );
  }

  private onClosed(code: number, reason = ''): void {
    const decision = closeDecision(code, this.handle, this.attempts);
    if (decision === 'reconnect') void this.reconnect();
    else void this.end(decision, null, closeDetail(code, reason));
  }

  /** Reopen the connection on the resumption handle, with a credential minted for it or a fresh one. */
  private async reconnect(minted?: LiveCredential): Promise<void> {
    const session = this.session;
    if (!session || this.ending) return;
    this.attempts += 1;
    this.store.getState().apply('socket_closed');
    this.generation += 1;
    if (this.transport?.audio.ownership === 'managed') {
      await this.transport.close().catch(() => undefined);
    } else {
      void this.transport?.close().catch(() => undefined);
    }
    try {
      const credential =
        minted ??
        (await this.deps.api.post<LiveCredential>(
          `/live/sessions/${session.session_id}/credential`,
          {}
        ));
      await this.connect(credential);
    } catch {
      const decision = closeDecision(1006, this.handle, this.attempts);
      if (decision === 'reconnect') void this.reconnect();
      else void this.end(decision, null, 'reconnect failed');
    }
  }

  // -- turns ------------------------------------------------------------------

  private onTranscript(role: LiveTranscriptRole, text: string): void {
    if (!this.turn.startedAt) this.turn.startedAt = Date.now();
    if (role === 'user') {
      this.turn.user += text;
      if (!this.store.getState().delegating) this.store.getState().setVoiceState('recording');
    } else {
      this.turn.assistant += text;
    }
    this.store.getState().pushCaption(role, text, this.captionBreak);
    this.captionBreak = false;
    // Words either way are activity (LIA's speech is also a hold while it plays).
    this.clock?.touch();
  }

  private onTurnComplete(): void {
    this.captionBreak = true;
    // A model that reports its idle status speaks several utterances per
    // task: only its IDLE ends the exchange (Extended Thinking, documented).
    if (this.session?.capabilities.reports_idle) return;
    void this.archiveTurn();
    this.settleVoiceState();
  }

  private onInteractionStatus(status: LiveInteractionStatus): void {
    if (status === 'in_progress') {
      const state = this.store.getState();
      if (state.voiceState === 'idle' || state.voiceState === 'recording') {
        state.setVoiceState('processing');
      }
      this.clock?.hold('provider');
      return;
    }
    this.clock?.release('provider');
    if (this.session?.capabilities.reports_idle) void this.archiveTurn();
    this.settleVoiceState();
  }

  /** Nothing is being said or done: the face rests. */
  private settleVoiceState(): void {
    if (!this.player?.isSpeaking && !this.store.getState().delegating) {
      this.store.getState().setVoiceState('idle');
    }
  }

  private async onDelegation(delegations: LiveDelegation[]): Promise<void> {
    if (this.session?.mode === 'direct') return this.onLookups(delegations);
    const bridge = this.bridge;
    if (!bridge) return;
    for (const delegation of delegations) {
      this.turn.delegated = true;
      const spoken = this.turn.user.trim() || null;
      this.store.getState().setDelegating(true);
      this.store.getState().setVoiceState('processing');
      this.clock?.hold('delegating');
      const result = await bridge.handle(delegation, spoken);
      this.store.getState().setDelegating(bridge.busy);
      if (!bridge.busy) this.clock?.release('delegating');
      if (result && this.transport?.isOpen) {
        this.transport.answerDelegation(result.id, result.result, result.delivery, result.note);
      }
    }
  }

  /**
   * A DIRECT session's function calls: each one a lookup the API runs on the
   * session (`POST /live/sessions/{id}/tools`), its text — a result or the
   * refusal the voice says — answered on the same call id, spoken at once.
   * The turn stays voice-only: nothing reaches the chat, the exchange is
   * archived like any other. A door that cannot be reached is answered with
   * the browser-held line; a session the API no longer holds closes this tab.
   */
  private async onLookups(delegations: LiveDelegation[]): Promise<void> {
    const session = this.session;
    if (!session) return;
    for (const delegation of delegations) {
      if (!delegation.call) continue;
      this.store.getState().setDelegating(true);
      this.store.getState().setVoiceState('processing');
      this.clock?.hold('delegating');
      const text = await this.runLookup(session, delegation.call.name, delegation.call.args);
      this.store.getState().setDelegating(false);
      this.clock?.release('delegating');
      if (text === null) return;
      if (this.transport?.isOpen) this.transport.answerDelegation(delegation.id, text, 'now');
    }
  }

  /** The tool door's text, the browser-held line on a failure, null once the session is gone. */
  private async runLookup(
    session: LiveSessionStart,
    name: string,
    args: Record<string, unknown>
  ): Promise<string | null> {
    try {
      const answer = await this.deps.api.post<LiveToolCallResponse>(
        `/live/sessions/${session.session_id}/tools`,
        { name, arguments: args }
      );
      if (this.session?.session_id !== session.session_id || this.ending) return null;
      const activity = parseActivity(answer.activity);
      if (activity) this.store.getState().recordActivity(activity);
      return answer.text;
    } catch (error) {
      if (isGone(error) && !this.ending) {
        void this.end('superseded');
        return null;
      }
      return this.config?.direct_lines.lookup_failed ?? '';
    }
  }

  /**
   * A voice-only exchange becomes two visible rows, at once; a delegated one
   * nothing. A DIRECT session posts its exchanges to the same door, which
   * KEEPS them in the record (no row, no id back) until the end, when they
   * become the person's own turn (ADR-301): the captions stay in the banner
   * meanwhile.
   */
  private async archiveTurn(): Promise<void> {
    const session = this.session;
    const turn = this.turn;
    this.turn = freshTurn();
    if (!session || turn.delegated) return;
    const body = turnBody(turn, session.turn_text_max_chars);
    if (!body) return;
    if (body.assistant_text) {
      const tone = inferToneFromContent({
        content: body.assistant_text,
        isError: false,
        hasArtifacts: false,
      });
      useEyesSignalsStore
        .getState()
        .setReaction(REGISTER_EXPRESSIONS[tone.register], toneAmplitude(tone), tone.accent);
    }
    try {
      const ids = await this.deps.api.post<LiveTurnResponse>(
        `/live/sessions/${session.session_id}/turns`,
        body
      );
      this.appendArchived(session, body, ids);
    } catch (error) {
      // The record is gone: a newer session of this account superseded this
      // one (or the cap and its grace passed). This tab must not keep talking
      // as if it were the session — close it, named.
      if (isGone(error) && !this.ending) {
        void this.end('superseded');
        return;
      }
      // Otherwise the provider keeps the exchange in its own context; the
      // thread misses a row the next reload cannot recover. Nothing else to do.
    }
  }

  /** The archived rows join the thread at once, each under the id the server gave it. */
  private appendArchived(session: LiveSessionStart, body: TurnBody, ids: LiveTurnResponse): void {
    const at = new Date();
    if (body.user_text && ids.user_message_id) {
      this.chat.appendMessage(this.row(ids.user_message_id, 'user', body.user_text, at, session));
    }
    if (body.assistant_text && ids.assistant_message_id) {
      this.chat.appendMessage(
        this.row(ids.assistant_message_id, 'assistant', body.assistant_text, at, session)
      );
    }
  }

  private row(
    id: string,
    role: LiveTranscriptRole,
    content: string,
    at: Date,
    session: LiveSessionStart
  ): Message {
    return {
      id,
      role,
      content,
      timestamp: at,
      metadata: {
        type: LIVE_TURN_TYPE,
        live_session_id: session.session_id,
        run_id: session.run_id,
      },
    };
  }

  // -- end --------------------------------------------------------------------

  private async closeBooks(
    session: LiveSessionStart,
    outcome: LiveOutcome,
    detail: string | null,
    audioDiagnostics: PcmPlayerDiagnostics | null
  ): Promise<void> {
    try {
      // The figures of the card are the server's (exact, ADR-185): the
      // client only says how the session ended — and why, in technical words.
      const summary = await this.deps.api.post<LiveEndResponse>(
        `/live/sessions/${session.session_id}/end`,
        {
          outcome,
          detail: detail ? detail.slice(0, LIVE_END_DETAIL_MAX_CHARS) : null,
          ...(audioDiagnostics ? { audio_diagnostics: audioDiagnostics } : {}),
          provider_conversation_id: this.providerConversationId,
        }
      );
      if (summary.summary_message_id) {
        this.chat.appendMessage(this.summaryRow(session, outcome, summary));
      }
      // The vendor's own bill, on the person's key: shown once, recorded nowhere.
      if (summary.vendor_bill) this.store.getState().setVendorBill(summary.vendor_bill);
    } catch {
      // The record may be gone (a session past its cap and grace): the books
      // are closed server-side by expiry, and the store still names the outcome.
    }
  }

  private summaryRow(
    session: LiveSessionStart,
    outcome: LiveOutcome,
    summary: LiveEndResponse
  ): Message {
    const usage = summary.usage;
    return {
      id: summary.summary_message_id ?? `live-summary-${session.session_id}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      ...(usage
        ? {
            tokensIn: usage.tokens_in,
            tokensOut: usage.tokens_out,
            tokensCache: usage.tokens_cache,
            costEur: usage.cost_eur,
            googleApiRequests: usage.google_api_requests,
          }
        : {}),
      metadata: {
        type: LIVE_SUMMARY_TYPE,
        live_session_id: session.session_id,
        run_id: session.run_id,
        live_summary: {
          outcome,
          duration_seconds: summary.duration_seconds,
          delegations: summary.delegations,
          voice_turns: summary.voice_turns,
          extensions: summary.extensions,
          mode: session.mode,
          // A DIRECT session's relay fate at the closing (ADR-301); the row
          // is rewritten server-side once the relayed turn settles, and the
          // thread reloads on the notice.
          ...(summary.relay ? { relay: summary.relay } : {}),
        },
        ...(usage
          ? {
              tokens_in: usage.tokens_in,
              tokens_out: usage.tokens_out,
              tokens_cache: usage.tokens_cache,
              cost_eur: usage.cost_eur,
              google_api_requests: usage.google_api_requests,
            }
          : {}),
      },
    };
  }

  private release(): void {
    this.transport = null;
    this.mic = null;
    this.player = null;
    this.bridge = null;
    this.clock = null;
    this.session = null;
    this.handle = null;
    this.ending = false;
  }

  // -- timers -----------------------------------------------------------------

  /**
   * The silence clock: started once the session is open, kept across
   * reconnections. The MODEL's own timeout (owner decision 2026-09-19): 0
   * means the session never ends on silence.
   */
  private startClock(): void {
    if (this.clock) {
      this.clock.touch();
      return;
    }
    const seconds = this.session?.idle_timeout_seconds ?? 0;
    if (seconds <= 0) return;
    this.clock = new ActivityClock({
      idleMs: seconds * 1000,
      countdownMs: LIVE_IDLE_COUNTDOWN_MS,
      onCountdown: msLeft =>
        this.store.getState().setIdleCountdown(msLeft === null ? null : Math.ceil(msLeft / 1000)),
      onIdle: () => void this.end('idle_timeout'),
    });
    this.clock.start();
  }

  /**
   * The cap: the session ends at `expiresAt`; `extension_prompt_seconds`
   * before it the extension is OFFERED (spec A8, explicit and unlimited in
   * number) — or, on a model whose cap is 0 (unlimited), taken SILENTLY: the
   * cap rolls on by extension slices and no dialog ever interrupts the person.
   */
  private armExpiry(expiresAt: string, extensions: number): void {
    this.clearTimer('expiry');
    this.clearTimer('extension');
    const at = new Date(expiresAt).getTime();
    if (!Number.isFinite(at)) return;
    this.store.getState().setExpiry(at, extensions);
    const inMs = Math.max(0, at - Date.now());
    this.timers.expiry = setTimeout(() => void this.end('expired'), inMs);
    const promptMs = (this.config?.extension_prompt_seconds ?? 0) * 1000;
    if (promptMs <= 0) return;
    const unlimited = this.session?.session_max_minutes === 0;
    this.timers.extension = setTimeout(
      () => {
        if (!isSessionOpen(this.store.getState().status)) return;
        if (unlimited) void this.extend();
        else this.store.getState().offerExtension(true);
      },
      Math.max(0, inMs - promptMs)
    );
  }

  /**
   * The spend ceiling the person set on the connector (ADR-300 wave 3): the
   * indicative meter ends the session when the cost it computes reaches it.
   * A token-billed model is checked on every usage report; a duration-billed
   * one tolls with the clock, so it is checked every second as well.
   */
  private checkBudget(): void {
    const { rates, budgetEur, meter, liveSince, status } = this.store.getState();
    if (rates === null || budgetEur === null || !isSessionOpen(status)) return;
    const elapsed = liveSince === null ? 0 : Math.floor((Date.now() - liveSince) / 1000);
    const seconds =
      rates.pricing_unit === 'per_1m_tokens' ? undefined : Math.max(meter.seconds ?? 0, elapsed);
    const cost = meterCost(meter, rates, seconds);
    if (cost !== null && cost.eur >= budgetEur) void this.end('budget_reached');
  }

  private startBudgetClock(): void {
    this.clearTimer('budget');
    const { rates, budgetEur } = this.store.getState();
    if (rates === null || budgetEur === null || rates.pricing_unit === 'per_1m_tokens') return;
    this.timers.budget = setInterval(() => this.checkBudget(), 1000);
  }

  private clearTimer(name: keyof typeof this.timers): void {
    const timer = this.timers[name];
    // One map for both kinds: an interval id clears through clearInterval.
    if (timer) {
      clearTimeout(timer);
      clearInterval(timer);
    }
    delete this.timers[name];
  }

  private clearTimers(): void {
    for (const name of Object.keys(this.timers) as Array<keyof typeof this.timers>) {
      this.clearTimer(name);
    }
  }
}

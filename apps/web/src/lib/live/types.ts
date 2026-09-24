/**
 * Wire contracts of the live mode (ADR-299), mirrors of the API's
 * `domains/live/schemas.py`. A change on one side is a change on both.
 */
import { RELAY_OUTCOMES } from '@/types/telephony';

/**
 * Every way a session ends — a RUNTIME list so the labels guard can walk it
 * and the API's own guard can read it (`LiveOutcome` in `schemas.py`).
 */
export const LIVE_OUTCOMES = [
  'ended',
  'expired',
  'idle_timeout',
  'hidden',
  'provider_closed',
  'resumption_failed',
  'error',
  'mic_denied',
  'superseded',
  'budget_reached',
] as const;

export type LiveOutcome = (typeof LIVE_OUTCOMES)[number];

export function isLiveOutcome(value: unknown): value is LiveOutcome {
  return typeof value === 'string' && (LIVE_OUTCOMES as readonly string[]).includes(value);
}

export type LiveEndOfSpeech = 'calm' | 'normal' | 'lively';
export type LiveResultDelivery = 'interrupt' | 'when_idle';

/** The person's live conversation reflexes (`users.live_preferences`). */
export interface LivePreferences {
  interruptions: boolean;
  end_of_speech: LiveEndOfSpeech;
  result_delivery: LiveResultDelivery;
}

/**
 * What one model can do, from the provider's documented rules — the controller
 * and the bridge branch on THIS, never on a provider id (spec A11).
 */
export interface LiveModelCapabilities {
  /** The model keeps talking while a delegated request runs. */
  async_delegation: boolean;
  /** A result may carry a delivery mode (now / when idle / silent). */
  delivery_scheduling: boolean;
  /** The provider says when its task is done: the idle truth is its signal, not a turn end. */
  reports_idle: boolean;
  /** The provider cancels pending delegations when the person interrupts it. */
  cancels_on_interruption: boolean;
  /** The setup carries the end-of-speech and interruption reflexes. */
  configurable_vad: boolean;
  /** A dropped connection can resume with a handle. */
  resumes: boolean;
  /** A thinking level is required by the model. */
  thinking: boolean;
  /**
   * The wire carries a tool schema, so a DIRECT session can declare LIA's
   * read-only tools on it (ADR-300 wave 4); false on a native delegation wire.
   */
  direct_tools: boolean;
  /**
   * The voice and every reflex are the provider portal's, for the agent: the
   * settings offer no voice and no sample (ADR-300 wave 4).
   */
  portal_voice: boolean;
  /**
   * The platform prices nothing of a session on this model: the meter shows
   * the clock alone, no spend ceiling can be set, and the vendor's own bill
   * comes with the end (ElevenLabs Agents, on the person's key).
   */
  vendor_billed: boolean;
}

/**
 * What a session is: the voice delegating every request to the chat
 * (`delegated`), or holding LIA's read-only tools itself and never acting
 * (`direct` — the phone's own line, ADR-300 wave 4).
 */
export type LiveSessionMode = 'delegated' | 'direct';

export interface LiveModel {
  /** For an agent: the voice model its configuration names (information; the vendor prices it). */
  voice_model?: string | null;
  /** For an agent: the LLM its configuration names (information; the vendor bills it). */
  llm?: string | null;
  /** The live provider id the model belongs to. */
  provider: string;
  name: string;
  /** A human name the provider gives the model (an agent's name); null when the id is the name. */
  label?: string | null;
  /** Levels the person may pick; empty when the model reasons on its own terms. */
  thinking_levels: string[];
  capabilities: LiveModelCapabilities;
}

export interface LiveModelsResponse {
  /** The discovered models the tariff table declares — the only ones offered. */
  models: LiveModel[];
  default_model: string;
  /** Discovered but undeclared under LLM pricing: named, never offered (ADR-300 wave 3). */
  unpriced: string[];
}

/**
 * The tariff of THIS session's model, for the banner's indicative meter
 * (ADR-300 wave 3): the session runs on the person's own key, the platform
 * records nothing of it, and the browser multiplies the provider's own usage
 * reports by these rates. `per_1m_tokens` carries text rates and, for a
 * speech-to-speech model, the audio pair; `per_audio_minute` / `per_audio_hour`
 * bill the session's duration.
 */
export interface LiveRates {
  pricing_unit: 'per_1m_tokens' | 'per_audio_minute' | 'per_audio_hour';
  input_unit_price: number;
  output_unit_price: number;
  audio_input_unit_price: number | null;
  audio_output_unit_price: number | null;
  usd_eur_rate: number;
}

/**
 * What the provider billed the person for the session, in ITS words — shown
 * at the end, never recorded (the platform re-bills nothing of a session on
 * the person's own key).
 */
export interface LiveVendorBill {
  provider: string;
  cost_usd: number | null;
  credits: number | null;
  llm_credits: number | null;
  call_credits: number | null;
  platform_credits: number | null;
  llm_model: string | null;
  tts_model: string | null;
  duration_seconds: number | null;
}

export interface LiveVoice {
  name: string;
  characteristic: string;
}

/** `POST /live/voices/sample` — one sentence in a voice, on the person's key. */
export interface LiveVoiceSampleResponse {
  audio_base64: string;
  sample_rate: number;
  format: 'wav';
}

export interface LiveVoicesResponse {
  /** The provider the voices belong to (the settings refuse a stale answer for another). */
  provider: string;
  voices: LiveVoice[];
  /** `discovered` = a listing endpoint answered; `published` = the vendored list. */
  provenance: 'discovered' | 'published' | 'portal';
  published_at: string | null;
  source: string | null;
}

/** One model's choices on a connector: its voice, its level, its two durations (0 = no limit). */
export interface LiveModelSettings {
  voice: string;
  thinking_level: string | null;
  /** Silence after which the session closes; 0 = never. */
  idle_timeout_seconds: number;
  /** Longest session before the extension is offered; 0 = unlimited (extended silently). */
  session_max_minutes: number;
}

/** The current model of a connector and its own settings — what a PUT carries whole. */
export interface LiveConnectorSettings extends LiveModelSettings {
  model: string;
  /**
   * The CONNECTOR's optional spend ceiling per session, in euros on the
   * person's own key (ADR-300 wave 3): the browser's indicative meter ends
   * the session when it is reached. null = none.
   */
  session_budget_eur: number | null;
}

export interface LiveConnectorActivateRequest {
  provider: string;
  api_key: string;
  model: string;
  voice: string;
  thinking_level: string | null;
}

export interface LiveConnectorResponse {
  provider: string;
  connector_type: string;
  status: string;
  settings: LiveConnectorSettings;
  /** Every model this connector remembers, by model id (the form reads the one switched to). */
  model_settings: Record<string, LiveModelSettings>;
  functionally_verified: boolean;
  /** What the connector's chosen model can do (the settings hide what it cannot). */
  capabilities: LiveModelCapabilities;
  /** Whether the sessions open on THIS provider (the account's choice). */
  active: boolean;
}

/** `GET /live/connectors` — every active live connector, and the one the sessions open on. */
export interface LiveConnectorsResponse {
  connectors: LiveConnectorResponse[];
  active_provider: string | null;
}

/** `GET /live/config` — every bound the browser honours, published because enforced. */
/** The range a per-model duration may take, besides the unlimited value. */
export interface LiveDurationBounds {
  min: number;
  max: number;
}

export interface LiveConfigResponse {
  /** The instance default for a model whose connector stores none. */
  session_max_minutes: number;
  session_max_bounds: LiveDurationBounds;
  idle_timeout_bounds: LiveDurationBounds;
  /** The per-model duration that means « no limit ». */
  unlimited_value: number;
  /** The most a per-session spend ceiling may be set to (euros). */
  session_budget_eur_max: number;
  /** Minutes one explicit extension adds to the cap. */
  extension_minutes: number;
  /** Seconds before the cap at which the extension is offered. */
  extension_prompt_seconds: number;
  connect_window_seconds: number;
  /** The instance default for a model whose connector stores none. */
  idle_timeout_seconds: number;
  hidden_grace_seconds: number;
  delegation_timeout_seconds: number;
  delegation_result_max_tokens: number;
  delegation_tool_name: string;
  turn_text_max_chars: number;
  /** `timed_out`, `result_cut`, `superseded`, `empty_request` — the bridge's lines. */
  delegation_lines: Record<string, string>;
  /** `lookup_failed` — what a DIRECT session answers its model when the tool door cannot be reached. */
  direct_lines: Record<string, string>;
  /** One delivery note per register of the tone vocabulary (ADR-253), for the bridge. */
  tone_lines: Record<string, string>;
}

/**
 * A credential for ONE connection of a session. Measured 2026-09-18: a
 * single-use token cannot reopen its session, so every reconnection asks
 * `POST /live/sessions/{id}/credential` for a fresh one.
 */
export interface LiveCredential {
  /** Single use: the provider's token (`token`), or LIA's nonce handed back with the SDP offer (`offer`). */
  credential: string;
  credential_expires_at: string;
  connect_deadline_at: string;
  /** How the browser opens the connection: itself with the credential, or through the API's offer exchange. */
  connection: 'token' | 'offer';
  /** The provider setup the client replays verbatim as its first frame (token connections; empty otherwise). */
  setup: Record<string, unknown>;
  audio_transport?: 'websocket' | 'webrtc';
}

/** `POST /live/sessions/{id}/offer` — the provider's SDP answer, exchanged on the person's key. */
export interface LiveOfferResponse {
  sdp: string;
}

/** `POST /live/sessions` — everything the browser needs to open the session. */
export interface LiveSessionStart extends LiveCredential {
  session_id: string;
  provider: string;
  model: string;
  run_id: string;
  /** The mode the session was opened in (the record's own column). */
  mode: LiveSessionMode;
  tool_names?: string[];
  /** The session's cap (ISO 8601); moved by every extension. */
  expires_at: string;
  /** This model's cap; 0 = unlimited: the client extends silently instead of asking. */
  session_max_minutes: number;
  /** This model's silence timeout; 0 = never. */
  idle_timeout_seconds: number;
  preferences: LivePreferences;
  /** What THIS session's model can do. */
  capabilities: LiveModelCapabilities;
  delegation_tool_name: string;
  delegation_timeout_seconds: number;
  delegation_result_max_tokens: number;
  turn_text_max_chars: number;
  /** This model's declared tariff (a model with no tariff never starts). */
  /** The model's declared tariff for the meter; null on a vendor-billed model (the clock alone). */
  rates: LiveRates | null;
  /** The connector's spend ceiling for this session (euros), if the person set one. */
  session_budget_eur: number | null;
}

export interface LiveTurnRequest {
  user_text: string | null;
  assistant_text: string | null;
  started_at: string;
  ended_at: string;
}

export interface LiveTurnResponse {
  user_message_id: string | null;
  assistant_message_id: string | null;
}

/** How the session ended, as the client saw it — the card's figures are the server's (ADR-185). */
export interface LiveEndRequest {
  outcome: LiveOutcome;
  /** Why, in technical words (a provider's close code and reason) — logged by the API, never shown. */
  detail?: string | null;
  /** The provider's own conversation id, when its wire named one: the API reads the vendor's bill under it. */
  provider_conversation_id?: string | null;
}

/** LIA's own spend over the session, in the chat meter's vocabulary. */
export interface LiveUsage {
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  cost_eur: number;
  google_api_requests: number;
}

export interface LiveEndResponse {
  summary_message_id: string | null;
  duration_seconds: number;
  delegations: number;
  voice_turns: number;
  extensions: number;
  usage: LiveUsage | null;
  /** The vendor's own bill of the session, when its wire names the conversation and it could be read. */
  vendor_bill?: LiveVendorBill | null;
  /**
   * A DIRECT session's relay fate at the closing (ADR-301): `scheduled` — the
   * words are becoming the person's own turn, off the request path — or
   * `empty`; the card is rewritten with the settled fate. Null for a
   * delegated session.
   */
  relay: LiveRelayFate | null;
}

/**
 * What became of a DIRECT session's words (ADR-301): `scheduled` at the
 * closing, then the relay's own outcome once the turn settled — the phone's
 * `RelayOutcome` vocabulary on the browser.
 */
export const LIVE_RELAY_FATES = ['scheduled', ...RELAY_OUTCOMES] as const;
export type LiveRelayFate = (typeof LIVE_RELAY_FATES)[number];

export function isLiveRelayFate(value: unknown): value is LiveRelayFate {
  return typeof value === 'string' && (LIVE_RELAY_FATES as readonly string[]).includes(value);
}

/** `POST /live/sessions/{id}/extend` — the cap moved; a fresh credential when the connection must be reopened. */
export interface LiveExtendResponse {
  expires_at: string;
  extensions: number;
  credential: LiveCredential | null;
}

export type LiveTranscriptRole = 'user' | 'assistant';

/**
 * A request the voice hands to LIA. `request` is the model's own wording
 * (Gemini writes it as the function argument) or null when the provider's
 * delegation carries no text (GPT-Live: an id and metadata — the request is
 * then composed from the transcript).
 */
export interface LiveDelegation {
  id: string;
  request: string | null;
  /**
   * The function the model called and what it filled in, on a wire that
   * carries tool calls: a DIRECT session reads its lookups here (ADR-300
   * wave 4). Absent on a native delegation wire.
   */
  call?: LiveFunctionCall;
}

/** A function call as the provider hands it: its declared name, its arguments. */
export interface LiveFunctionCall {
  name: string;
  args: Record<string, unknown>;
}

/** `POST /live/sessions/{id}/tools` — one lookup a DIRECT session asked the API for. */
export interface LiveToolCallResponse {
  /** Optional execution evidence; ok alone is only admission. */
  activity?: unknown;
  /** The projected result, or the refusal the voice says. */
  text: string;
  /** Admission only; actual execution outcome is carried by activity. */
  ok: boolean;
}

/** How a delegated answer reaches the voice: spoken at once, at the next pause, or kept silent. */
export type LiveDelivery = 'now' | 'when_idle' | 'silent';

/** The provider's word on its own task: still working, or done and waiting for the person. */
export type LiveInteractionStatus = 'in_progress' | 'idle';

/**
 * What a transport does with the audio. `pcm`: the controller captures 16-bit
 * frames at `inputRate` and plays the frames the transport hands back at
 * `outputRate`. `native`: the transport carries the tracks itself (WebRTC) —
 * it takes the microphone's stream and plays what it receives.
 */
export interface LiveTransportAudio {
  ownership: 'pcm' | 'native' | 'managed';
  inputRate: number;
  outputRate: number;
  /** The microphone chunk the transport wants, in milliseconds. */
  chunkMs: number;
}

/** What a transport reports; every handler is optional for the caller. */
/**
 * The provider's own usage report, normalised (ADR-300 wave 3): tokens by
 * modality for a token-billed model (one report per model turn, the prompt
 * being the WHOLE context re-billed), the session's seconds for a
 * duration-billed one. Counted in the browser on the person's key — the
 * banner's indicative meter — and recorded nowhere.
 */
export interface LiveUsageReport {
  tokens?: {
    textIn: number;
    audioIn: number;
    textOut: number;
    audioOut: number;
    /** Thinking tokens, billed at the text output rate. */
    thoughts: number;
    /** The context size this turn (prompt + response). */
    context: number;
  };
  duration?: {
    /** The session's seconds so far, cumulative. */
    seconds: number;
    /** The share of the context window in use, 0..1, when reported. */
    contextRatio: number | null;
  };
}

export interface LiveTransportEvents {
  /** The provider acknowledged the setup: the session is open. */
  onReady?: () => void;
  /** The provider reported its usage (a model turn, or a periodic tick). */
  onUsage?: (report: LiveUsageReport) => void;
  /** Raw PCM 16-bit LE at the transport's `outputRate` (pcm ownership only). */
  onAudio?: (pcm16: ArrayBuffer) => void;
  /** The provider's voice started or stopped (native ownership only). */
  onSpeakingChange?: (speaking: boolean) => void;
  onTranscript?: (role: LiveTranscriptRole, text: string) => void;
  /** One spoken turn ended (a model that reports its idle status emits one per utterance). */
  onTurnComplete?: () => void;
  /** The model finished generating the current response. */
  onGenerationComplete?: () => void;
  onInteractionStatus?: (status: LiveInteractionStatus) => void;
  onInterrupted?: () => void;
  onDelegation?: (delegations: LiveDelegation[]) => void;
  onDelegationCancelled?: (ids: string[]) => void;
  /** Milliseconds before the provider closes the connection. */
  onGoAway?: (timeLeftMs: number) => void;
  onResumption?: (handle: string, resumable: boolean) => void;
  /** The provider named its own conversation (ElevenLabs' metadata): the end reads the vendor's bill under it. */
  onProviderConversation?: (conversationId: string) => void;
  /** The wire closed: the code and the provider's reason travel to the API's log. */
  onClosed?: (code: number, reason: string) => void;
  onError?: (error: Error) => void;
}

export interface LiveConnectOptions {
  credential: string;
  setup: Record<string, unknown>;
  toolNames?: string[];
  resumptionHandle?: string | null;
  /** What the session's model can do — the transport shapes its wire from it. */
  capabilities: LiveModelCapabilities;
  /** The microphone, for a transport that carries the audio itself. */
  microphone?: MediaStream | null;
  /**
   * The API's offer exchange (`POST /live/sessions/{id}/offer`), for an
   * `offer` connection: the SDP offer goes in with the credential, the
   * provider's answer comes back.
   */
  exchangeOffer?: (credential: string, sdp: string) => Promise<string>;
}

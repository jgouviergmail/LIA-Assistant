/**
 * One archived conversation message, as the history endpoints return it.
 *
 * Mirrors the backend Pydantic contract `ConversationMessageResponse` in
 * `apps/api/src/domains/conversations/schemas.py`. Field names are the wire names.
 * Kept free of imports so the hermetic E2E suite, whose TypeScript project does
 * not resolve the `@/` alias, can type its mocked history with the real shape.
 */
export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  message_metadata: Record<string, unknown> | null; // API uses Pydantic alias "message_metadata"
  created_at: string;
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_cache: number | null;
  cost_eur: number | null;
  google_api_requests: number | null;
  // Per-message STT cost (only for user messages produced by a remote
  // transcription provider). All NULL for assistant messages and for typed
  // text / local-Sherpa user messages.
  stt_provider: string | null;
  stt_audio_duration_seconds: number | null;
  stt_cost_eur: number | null;
  // Per-message TTS cost (only for assistant messages synthesised by a
  // paid TTS provider — Edge stays NULL). Mirror of STT pattern.
  tts_provider: string | null;
  tts_model: string | null;
  tts_characters: number | null;
  tts_cost_eur: number | null;
}

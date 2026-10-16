/**
 * The brand a voice engine goes by wherever a person reads it (ADR-345): the
 * chat's synthesis and transcription cost tooltips, the voice settings. A name,
 * never translated — each one the API's own display name (``LLM_PROVIDERS``),
 * held equal by ``test_voice_provider_brands_guard.py``. An engine this table
 * does not know is shown by its identifier.
 */
export const VOICE_PROVIDER_BRANDS: ReadonlyMap<string, string> = new Map([
  ['edge', 'Edge TTS (Microsoft)'],
  ['elevenlabs', 'ElevenLabs'],
  ['fishaudio', 'Fish Audio'],
  ['gemini', 'Google Gemini'],
  ['openai', 'OpenAI'],
]);

/** The brand of ``provider``, or the identifier itself when no brand is declared. */
export function voiceProviderBrand(provider: string): string {
  return VOICE_PROVIDER_BRANDS.get(provider) ?? provider;
}

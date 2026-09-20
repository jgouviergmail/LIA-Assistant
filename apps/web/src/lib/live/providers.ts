/**
 * The live providers this browser speaks (ADR-299, wave 2 spec A10/A11): one
 * row per provider — the id the API names, the connector type it is stored
 * as, the brand shown beside its models and the account its sessions are
 * billed to. A second provider is one row here, one transport in
 * `transports/`, one connector type.
 */
export interface LiveProviderInfo {
  /** The provider id on the wire (`LiveSessionStart.provider`, `LiveModel.provider`). */
  id: string;
  /** The connector type the key is stored as. */
  connectorType: string;
  /** The brand, as a product name (never translated). */
  label: string;
  /** The account the person's sessions are billed to (never translated). */
  account: string;
}

export const LIVE_PROVIDERS: readonly LiveProviderInfo[] = [
  { id: 'gemini', connectorType: 'gemini_live', label: 'Gemini', account: 'Google AI' },
  { id: 'openai', connectorType: 'gpt_live', label: 'OpenAI', account: 'OpenAI' },
  {
    id: 'elevenlabs',
    connectorType: 'elevenlabs_live',
    label: 'ElevenLabs',
    account: 'ElevenLabs',
  },
];

/**
 * The voice stored for a model whose voice is the provider portal's (a
 * `portal_voice` capability, ADR-300 wave 4): a sentinel the API knows,
 * never offered, never sampled. The backend guard holds it equal to its own.
 */
export const LIVE_PORTAL_VOICE = 'agent';

export function liveProviderLabel(id: string): string {
  return LIVE_PROVIDERS.find(p => p.id === id)?.label ?? id;
}

/** Whether a stored connector type (any case) belongs to the live category. */
export function isLiveConnectorType(connectorType: string): boolean {
  const wanted = connectorType.toLowerCase();
  return LIVE_PROVIDERS.some(p => p.connectorType === wanted);
}

export function liveProviderAccount(id: string): string {
  return LIVE_PROVIDERS.find(p => p.id === id)?.account ?? id;
}

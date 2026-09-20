/**
 * The live connector form (ADR-299, spec A10): key → validate → discover the
 * models and the voices → choose → activate.
 *
 * The key is verified by the very listing that fills the model select
 * (`POST /live/models/discover`), so there is no second round-trip; the
 * voices come from the provider's published list with its provenance. The
 * provider is the authority on the pair: the activation probes it, and its
 * refusal comes back in its own words (`detail.message`).
 *
 * Editing the key invalidates the discovered models (they belong to the old
 * key's account). An activation declares the live connectors changed
 * (`live_connectors` revision): the header's voice menu re-reads them.
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '@/lib/api-client';
import { getApiErrorDetail } from '@/lib/api-error';
import type {
  LiveConnectorActivateRequest,
  LiveModel,
  LiveModelsResponse,
  LiveVoicesResponse,
} from '@/lib/live/types';
import { LIVE_PORTAL_VOICE } from '@/lib/live/providers';
import { logger } from '@/lib/logger';
import { bumpRevision } from '@/stores/revisionStore';

interface UseLiveConnectorOptions {
  /** The live provider this form sets up. */
  provider: string;
  onSuccess?: () => void;
}

/** The level a model offers for a choice: the current one when on the ladder, else the first. */
function levelFor(model: LiveModel | undefined, current: string | null): string | null {
  const levels = model?.thinking_levels ?? [];
  if (levels.length === 0) return null;
  return current && levels.includes(current) ? current : levels[0];
}

export function useLiveConnector({ provider, onSuccess }: UseLiveConnectorOptions) {
  const { t } = useTranslation();
  const [apiKey, setApiKeyRaw] = useState('');
  const [models, setModels] = useState<LiveModel[]>([]);
  const [voices, setVoices] = useState<LiveVoicesResponse | null>(null);
  const [model, setModelRaw] = useState<string | null>(null);
  const [voice, setVoice] = useState<string | null>(null);
  const [thinkingLevel, setThinkingLevelRaw] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [activated, setActivated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setApiKey = useCallback((value: string) => {
    setApiKeyRaw(value);
    setModels([]);
    setModelRaw(null);
    setThinkingLevelRaw(null);
  }, []);

  const setModel = useCallback(
    (name: string) => {
      const chosen = models.find(m => m.name === name);
      setModelRaw(name);
      setThinkingLevelRaw(current => levelFor(chosen, current));
      // A portal-voiced model (an agent) takes the sentinel: no voice to choose.
      if (chosen?.capabilities.portal_voice) setVoice(LIVE_PORTAL_VOICE);
    },
    [models]
  );

  const validateKey = useCallback(async () => {
    setIsValidating(true);
    setError(null);
    try {
      const [discovered, listing] = await Promise.all([
        apiClient.post<LiveModelsResponse>('/live/models/discover', { provider, api_key: apiKey }),
        apiClient.get<LiveVoicesResponse>(
          `/live/voices/published?provider=${encodeURIComponent(provider)}`
        ),
      ]);
      if (discovered.models.length === 0) {
        // A working key whose live models are all undeclared under LLM pricing
        // is not an invalid key: the models are named so an administrator can
        // declare them (ADR-300 wave 3).
        setError(
          discovered.unpriced.length > 0
            ? t('settings.connectors.live.no_priced_model', {
                models: discovered.unpriced.join(', '),
              })
            : t('settings.connectors.live.invalid_key')
        );
        return;
      }
      const preselected =
        discovered.models.find(m => m.name === discovered.default_model) ?? discovered.models[0];
      setModels(discovered.models);
      setModelRaw(preselected.name);
      setThinkingLevelRaw(levelFor(preselected, null));
      setVoices(listing);
      setVoice(current =>
        preselected.capabilities.portal_voice
          ? LIVE_PORTAL_VOICE
          : (current ?? listing.voices[0]?.name ?? null)
      );
    } catch (err) {
      logger.error('live_key_validation_failed', err as Error, { component: 'useLiveConnector' });
      setError(getApiErrorDetail(err) ?? t('settings.connectors.live.invalid_key'));
    } finally {
      setIsValidating(false);
    }
  }, [apiKey, provider, t]);

  const selectedModel = models.find(m => m.name === model);
  const thinkingLevels = selectedModel?.thinking_levels ?? [];
  const canActivate = Boolean(model && voice && !isActivating && !isValidating);

  const activate = useCallback(async () => {
    if (!model || !voice || isActivating) return;
    setIsActivating(true);
    setError(null);
    const payload: LiveConnectorActivateRequest = {
      provider,
      api_key: apiKey,
      model,
      voice,
      thinking_level: thinkingLevels.length > 0 ? thinkingLevel : null,
    };
    try {
      await apiClient.post('/live/connector/activate', payload);
      setActivated(true);
      bumpRevision('live_connectors');
      onSuccess?.();
    } catch (err) {
      logger.error('live_activation_failed', err as Error, { component: 'useLiveConnector' });
      setError(getApiErrorDetail(err) ?? t('common.error'));
    } finally {
      setIsActivating(false);
    }
  }, [
    provider,
    apiKey,
    model,
    voice,
    thinkingLevel,
    thinkingLevels.length,
    isActivating,
    onSuccess,
    t,
  ]);

  return {
    apiKey,
    setApiKey,
    models,
    voices,
    model,
    setModel,
    voice,
    setVoice,
    thinkingLevel,
    setThinkingLevel: setThinkingLevelRaw,
    thinkingLevels,
    validateKey,
    activate,
    isValidating,
    isActivating,
    activated,
    error,
    canActivate,
  };
}

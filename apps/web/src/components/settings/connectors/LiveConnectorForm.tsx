'use client';

/**
 * Live (Gemini) connector — single-screen configuration (ADR-299, spec A10).
 *
 * Key, then — once the key is validated by the very listing that fills the
 * select — the model, the voice (with the published list's provenance) and,
 * ONLY for a model that declares a ladder, the thinking level; one Activate
 * button. Sessions run on the person's own provider account (D-9 doctrine):
 * surfaced as a notice. No model label is invented: the provider's name, as
 * listed.
 */

import { AudioLines, KeyRound, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { VoicesProvenance } from '@/components/live/VoicesProvenance';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Language } from '@/i18n/settings';

import { useVoiceSample } from '@/hooks/useVoiceSample';
import { liveProviderAccount, liveProviderLabel } from '@/lib/live/providers';

import { useLiveConnector } from './hooks/useLiveConnector';

interface LiveConnectorFormProps {
  lng: Language;
  /** The live provider this form sets up (`gemini` …). */
  provider: string;
  onSuccess?: () => void;
  onCancel?: () => void;
}

/** The voice of a voiced model: the provider's list with its provenance, a sample on every change. */
function VoiceStep({
  lng,
  provider,
  form,
}: {
  lng: Language;
  provider: string;
  form: ReturnType<typeof useLiveConnector>;
}) {
  const { t } = useTranslation();
  const sample = useVoiceSample();
  return (
    <div className="space-y-3">
      <Label htmlFor="live-connector-voice">{t('settings.connectors.live.step_voice')}</Label>
      <div className="flex items-center gap-2">
        <Select
          value={form.voice ?? ''}
          onValueChange={voice => {
            form.setVoice(voice);
            void sample.play(voice, form.apiKey, provider);
          }}
        >
          <SelectTrigger id="live-connector-voice" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(form.voices?.voices ?? []).map(voice => (
              <SelectItem key={voice.name} value={voice.name}>
                {voice.characteristic ? `${voice.name} — ${voice.characteristic}` : voice.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 min-w-11 shrink-0"
          aria-label={`${t('settings.live_mode.voice_sample')} — ${form.voice ?? ''}`}
          title={t('settings.live_mode.voice_sample')}
          disabled={sample.playing || !form.voice}
          onClick={() => form.voice && void sample.play(form.voice, form.apiKey, provider)}
        >
          <Volume2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <VoicesProvenance lng={lng} voices={form.voices ?? undefined} />
    </div>
  );
}

export function LiveConnectorForm({ lng, provider, onSuccess, onCancel }: LiveConnectorFormProps) {
  const { t } = useTranslation();
  const form = useLiveConnector({ provider, onSuccess });
  const brand = liveProviderLabel(provider);
  const discovered = form.models.length > 0;
  const keyReady = form.apiKey.trim().length >= 8;
  // A provider whose « models » are the person's agents (ADR-300 wave 4): the
  // voice is the portal's, so the step is named « agent » and no voice is offered.
  const chosen = form.models.find(m => m.name === form.model);
  const portalVoice = chosen?.capabilities.portal_voice === true;

  if (form.activated) {
    return (
      <div className="space-y-3 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
          <AudioLines className="h-8 w-8 text-green-500" aria-hidden="true" />
        </div>
        <p className="text-sm font-medium text-green-600">
          {t('settings.connectors.live.activated')}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
        {t('settings.connectors.live.billing_notice', { account: liveProviderAccount(provider) })}
      </div>

      {/* Section 1 — API key + inline validation */}
      <div className="space-y-3">
        <Label id="live-api-key-label" htmlFor="live-api-key">
          {t('settings.connectors.live.step_key', { brand })}
        </Label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <KeyRound
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              aria-hidden="true"
            />
            {/* `aria-labelledby` beside `htmlFor`: the a11y lint cannot follow a
                label association across components (frontend charter). */}
            <input
              id="live-api-key"
              aria-labelledby="live-api-key-label"
              type="password"
              autoComplete="off"
              value={form.apiKey}
              onChange={event => form.setApiKey(event.target.value)}
              placeholder={t('settings.connectors.live.key_placeholder', { brand })}
              className="w-full rounded-lg border border-input bg-background py-2 pl-9 pr-3 text-sm"
            />
          </div>
          {/* aria-label keeps the button named while the spinner replaces its text. */}
          <Button
            type="button"
            onClick={() => {
              if (keyReady) void form.validateKey();
            }}
            isLoading={form.isValidating}
            aria-disabled={!keyReady}
            aria-label={t('settings.connectors.live.validate_key')}
            className="shrink-0 aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
          >
            {t('settings.connectors.live.validate_key')}
          </Button>
        </div>
      </div>

      {/* Section 2 — model, voice, thinking level (once the key is validated) */}
      {discovered ? (
        <div className="space-y-4">
          <div className="space-y-3">
            <Label htmlFor="live-connector-model">
              {t(
                portalVoice
                  ? 'settings.connectors.live.step_agent'
                  : 'settings.connectors.live.step_model'
              )}
            </Label>
            <Select value={form.model ?? ''} onValueChange={form.setModel}>
              <SelectTrigger id="live-connector-model" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {form.models.map(model => (
                  <SelectItem key={model.name} value={model.name}>
                    {model.label ?? model.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {portalVoice ? (
            <p className="text-xs text-muted-foreground" data-testid="live-voice-portal">
              {t('settings.live_mode.voice_portal', { brand })}
            </p>
          ) : (
            <VoiceStep lng={lng} provider={provider} form={form} />
          )}

          {form.thinkingLevels.length > 0 && (
            <div className="space-y-3">
              <Label htmlFor="live-connector-thinking">
                {t('settings.connectors.live.step_thinking')}
              </Label>
              <Select
                value={form.thinkingLevel ?? form.thinkingLevels[0]}
                onValueChange={form.setThinkingLevel}
              >
                <SelectTrigger id="live-connector-thinking" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {form.thinkingLevels.map(level => (
                    <SelectItem key={level} value={level}>
                      {level}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-gray-200 p-3 text-xs text-gray-500 dark:border-gray-700">
          {t('settings.connectors.live.models_hint')}
        </p>
      )}

      {/* Single Activate button — named while busy, guarded rather than disabled. */}
      <Button
        type="button"
        onClick={() => {
          if (form.canActivate) void form.activate();
        }}
        isLoading={form.isActivating}
        aria-disabled={!form.canActivate}
        aria-label={t('settings.connectors.live.activate')}
        className="w-full aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
      >
        {t('settings.connectors.live.activate')}
      </Button>

      {form.error && (
        <div
          role="alert"
          className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400"
        >
          {form.error}
        </div>
      )}

      <Button type="button" variant="outline" onClick={onCancel} className="w-full">
        {t('common.cancel')}
      </Button>
    </div>
  );
}

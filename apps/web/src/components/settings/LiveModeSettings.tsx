'use client';

/**
 * LiveModeSettings — the live connectors' model, voice and thinking level,
 * and the person's four conversation reflexes (ADR-299, spec A10 bis; wave 2
 * A10: the category is additive, so the model list is the UNION of every
 * active key's models, grouped by provider, and choosing a model IS choosing
 * the provider the sessions open on).
 *
 * Renders nothing when the instance flag is off (the sandbox-egress
 * precedent); gated in `settings-search.ts` on the same flag. Without a
 * connector the section points at the connectors section rather than showing
 * three empty lists — the connector is created THERE, with its key.
 *
 * The provider judges the model again on every save (a probe), and its
 * refusal is shown in its own words, in a `role="alert"`.
 */

import { AudioLines, Plug, SlidersHorizontal, Volume2 } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { Button } from '@/components/ui/button';
import { FormSection } from '@/components/ui/form-section';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { VoicesProvenance } from '@/components/live/VoicesProvenance';
import { Switch } from '@/components/ui/switch';
import { useAppConfig } from '@/hooks/useAppConfig';
import { activeLiveConnector, useLiveConnectorSettings } from '@/hooks/useLiveConnectorSettings';
import { modelKey, useLiveConnectorDraft } from '@/hooks/useLiveConnectorDraft';
import { LiveBudgetField } from '@/components/settings/LiveBudgetField';
import { LiveDurationFields } from '@/components/settings/LiveDurationFields';
import { useLivePreferences } from '@/hooks/useLivePreferences';
import { useVoiceSample } from '@/hooks/useVoiceSample';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { liveProviderLabel } from '@/lib/live/providers';
import type { LiveModelLookup } from '@/hooks/useLiveConnectorDraft';
import type {
  LiveConfigResponse,
  LiveConnectorResponse,
  LiveConnectorSettings,
  LiveModel,
  LiveModelsResponse,
  LivePreferences,
  LiveVoicesResponse,
} from '@/lib/live/types';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { BaseSettingsProps } from '@/types/settings';

export function LiveModeSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const flagOn = !!config?.features?.live_enabled;
  // The provider under edit in the form (its voices are listed); the active one until a choice.
  const [editedProvider, setEditedProvider] = useState<string | null>(null);
  const connector = useLiveConnectorSettings(flagOn, editedProvider);
  const preferences = useLivePreferences(flagOn);
  const configurableVad =
    activeLiveConnector(connector.connectors)?.capabilities.configurable_vad ?? true;

  if (!flagOn) return null;

  return (
    <SettingsSection
      value="live-mode"
      title={t('settings.live_mode.title')}
      description={t('settings.live_mode.description')}
      icon={AudioLines}
    >
      <div className="space-y-6">
        <FormSection icon={Plug} title={t('settings.live_mode.connector_title')}>
          <ConnectorPanel lng={lng} state={connector} onProviderChange={setEditedProvider} />
        </FormSection>
        <FormSection icon={SlidersHorizontal} title={t('settings.live_mode.preferences_title')}>
          <PreferencesPanel lng={lng} state={preferences} configurableVad={configurableVad} />
        </FormSection>
      </div>
    </SettingsSection>
  );
}

// -- connector ----------------------------------------------------------------

function ConnectorPanel({
  lng,
  state,
  onProviderChange,
}: {
  lng: Language;
  state: ReturnType<typeof useLiveConnectorSettings>;
  onProviderChange: (provider: string) => void;
}) {
  const { t } = useTranslation(lng);
  const active = activeLiveConnector(state.connectors);
  if (state.connectors === undefined || state.loading) {
    return <Skeleton className="h-24 w-full" />;
  }
  if (!active) {
    return (
      <p className="text-sm text-muted-foreground">
        {t('settings.live_mode.connector_missing')}{' '}
        <Link
          href={settingsSectionHref(lng, 'connectors')}
          className="font-medium text-primary underline underline-offset-2"
        >
          {t('settings.live_mode.connector_link')}
        </Link>
      </p>
    );
  }
  if (!state.config) {
    return <Skeleton className="h-24 w-full" />;
  }
  const draftKey = `${active.provider}|${active.settings.model}|${active.settings.voice}|${active.settings.thinking_level ?? ''}|${active.settings.idle_timeout_seconds}|${active.settings.session_max_minutes}|${active.settings.session_budget_eur ?? ''}`;
  const connectors = state.connectors.connectors;
  return (
    <ConnectorForm
      key={draftKey}
      lng={lng}
      connector={active}
      config={state.config}
      lookup={(provider, model) =>
        connectors.find(c => c.provider === provider)?.model_settings[model]
      }
      budgetOf={provider =>
        connectors.find(c => c.provider === provider)?.settings.session_budget_eur ?? null
      }
      models={state.models}
      voices={state.voices}
      saving={state.saving}
      saveError={state.saveError}
      onSave={state.save}
      onProviderChange={onProviderChange}
    />
  );
}

type DraftState = ReturnType<typeof useLiveConnectorDraft>;

function ConnectorForm({
  lng,
  connector,
  config,
  lookup,
  budgetOf,
  models,
  voices,
  saving,
  saveError,
  onSave,
  onProviderChange,
}: {
  lng: Language;
  connector: LiveConnectorResponse;
  config: LiveConfigResponse;
  lookup: LiveModelLookup;
  budgetOf: (provider: string) => number | null;
  models: LiveModelsResponse | undefined;
  voices: LiveVoicesResponse | undefined;
  saving: boolean;
  saveError: string | null;
  onSave: (provider: string, settings: LiveConnectorSettings) => Promise<boolean>;
  onProviderChange: (provider: string) => void;
}) {
  const { t } = useTranslation(lng);
  const state = useLiveConnectorDraft(
    connector,
    models?.models ?? [],
    voices,
    lookup,
    {
      defaults: {
        idle_timeout_seconds: config.idle_timeout_seconds,
        session_max_minutes: config.session_max_minutes,
      },
      idle_bounds: config.idle_timeout_bounds,
      session_bounds: config.session_max_bounds,
      unlimited: config.unlimited_value,
      budget_max: config.session_budget_eur_max,
    },
    onProviderChange,
    budgetOf
  );

  const submit = async () => {
    if (saving || !state.dirty || !state.toSave) return;
    const ok = await onSave(state.draft.provider, state.toSave);
    if (ok) toast.success(t('settings.live_mode.saved'));
  };

  return (
    <div className="space-y-4">
      <ModelSelect
        lng={lng}
        state={state}
        models={models?.models ?? []}
        unpriced={models?.unpriced ?? []}
        disabled={saving}
      />
      {state.selectedModel?.capabilities.portal_voice ? (
        <p className="text-xs text-muted-foreground" data-testid="live-voice-portal">
          {t('settings.live_mode.voice_portal', {
            brand: liveProviderLabel(state.draft.provider),
          })}
        </p>
      ) : (
        <VoiceSelect lng={lng} state={state} voices={voices} disabled={saving} />
      )}
      {state.levels.length > 0 && (
        <div className="space-y-3">
          <Label htmlFor="live-thinking">{t('settings.live_mode.thinking')}</Label>
          <Select
            value={state.draft.thinking_level ?? state.levels[0]}
            onValueChange={state.chooseLevel}
            disabled={saving}
          >
            <SelectTrigger id="live-thinking" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {state.levels.map(level => (
                <SelectItem key={level} value={level}>
                  {level}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <LiveDurationFields
        // A model switched to brings its own numbers: whatever was being typed goes.
        key={`${state.draft.provider}|${state.draft.model}`}
        lng={lng}
        idleTimeoutSeconds={state.draft.idle_timeout_seconds}
        sessionMaxMinutes={state.draft.session_max_minutes}
        idleBounds={config.idle_timeout_bounds}
        sessionBounds={config.session_max_bounds}
        unlimited={config.unlimited_value}
        idleAllowed={state.idleAllowed}
        sessionAllowed={state.sessionAllowed}
        disabled={saving}
        onIdleTimeout={state.chooseIdleTimeout}
        onSessionMax={state.chooseSessionMax}
      />
      {state.selectedModel?.capabilities.vendor_billed ? (
        <p className="text-xs text-muted-foreground">
          {t('settings.live_mode.vendor_billed', {
            brand: liveProviderLabel(state.draft.provider),
          })}
        </p>
      ) : (
        <LiveBudgetField
          // The ceiling is the connector's: a provider switched to brings its own.
          key={state.draft.provider}
          lng={lng}
          provider={liveProviderLabel(state.draft.provider)}
          value={state.draft.session_budget_eur}
          max={config.session_budget_eur_max}
          invalid={!state.budgetAllowed}
          disabled={saving}
          onChange={state.chooseBudget}
        />
      )}

      {saveError && (
        <p role="alert" className="text-sm text-destructive">
          {saveError}
        </p>
      )}

      <Button
        type="button"
        onClick={() => void submit()}
        isLoading={saving}
        aria-disabled={!state.dirty || !state.toSave}
        className="aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
      >
        {t('settings.live_mode.save')}
      </Button>
    </div>
  );
}

/** The union of models, grouped by provider in the listing's order. */
function groupByProvider(models: readonly LiveModel[]): Array<[string, LiveModel[]]> {
  const groups = new Map<string, LiveModel[]>();
  for (const model of models) {
    const group = groups.get(model.provider) ?? [];
    group.push(model);
    groups.set(model.provider, group);
  }
  return [...groups.entries()];
}

function ModelSelect({
  lng,
  state,
  models,
  unpriced,
  disabled,
}: {
  lng: Language;
  state: DraftState;
  models: readonly LiveModel[];
  /** Discovered on the keys but undeclared under LLM pricing — said, never offered. */
  unpriced: readonly string[];
  disabled: boolean;
}) {
  const { t } = useTranslation(lng);
  const current = modelKey(state.draft.provider, state.draft.model);
  return (
    <div className="space-y-3">
      <Label htmlFor="live-model">{t('settings.live_mode.model')}</Label>
      <Select value={current} onValueChange={state.chooseModelKey} disabled={disabled}>
        <SelectTrigger
          id="live-model"
          className="w-full"
          aria-describedby={unpriced.length > 0 ? 'live-model-unpriced' : undefined}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {/* The stored model stays choosable even when today's listing
              dropped it — shown, so the trigger never reads empty. */}
          {!state.selectedModel && <SelectItem value={current}>{state.draft.model}</SelectItem>}
          {groupByProvider(models).map(([provider, group]) => (
            <SelectGroup key={provider}>
              <SelectLabel>{liveProviderLabel(provider)}</SelectLabel>
              {group.map(model => (
                <SelectItem
                  key={modelKey(provider, model.name)}
                  value={modelKey(provider, model.name)}
                >
                  {model.label ?? model.name}
                  {model.llm && (
                    <span className="text-muted-foreground">
                      {' '}
                      ·{' '}
                      {t('settings.live_mode.agent_models', {
                        voice: model.voice_model ?? '?',
                        llm: model.llm,
                      })}
                    </span>
                  )}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      {unpriced.length > 0 && (
        <p id="live-model-unpriced" className="text-xs text-muted-foreground">
          {t('settings.live_mode.unpriced', { models: unpriced.join(', ') })}
        </p>
      )}
    </div>
  );
}

function VoiceSelect({
  lng,
  state,
  voices,
  disabled,
}: {
  lng: Language;
  state: DraftState;
  voices: LiveVoicesResponse | undefined;
  disabled: boolean;
}) {
  const { t } = useTranslation(lng);
  const sample = useVoiceSample();
  const { voice, draft } = state;
  const options = voices?.voices ?? [];
  return (
    <div className="space-y-3">
      <Label htmlFor="live-voice">{t('settings.live_mode.voice')}</Label>
      <div className="flex items-center gap-2">
        <Select
          value={voice}
          onValueChange={chosen => {
            state.chooseVoice(chosen);
            void sample.play(chosen, undefined, draft.provider);
          }}
          disabled={disabled || voices === undefined}
        >
          <SelectTrigger id="live-voice" className="w-full" aria-describedby="live-voice-help">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {/* The stored voice stays shown while the listing loads or dropped it. */}
            {voice && !options.some(option => option.name === voice) && (
              <SelectItem value={voice}>{voice}</SelectItem>
            )}
            {options.map(option => (
              <SelectItem key={option.name} value={option.name}>
                {option.characteristic ? `${option.name} — ${option.characteristic}` : option.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 min-w-11 shrink-0"
          aria-label={`${t('settings.live_mode.voice_sample')} — ${voice}`}
          title={t('settings.live_mode.voice_sample')}
          disabled={sample.playing || disabled || !voice}
          onClick={() => void sample.play(voice, undefined, draft.provider)}
        >
          <Volume2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <p id="live-voice-help" className="text-xs text-muted-foreground">
        {t('settings.live_mode.voice_sample_help')}
      </p>
      <VoicesProvenance lng={lng} voices={voices} />
    </div>
  );
}

function PreferencesPanel({
  lng,
  state,
  configurableVad,
}: {
  lng: Language;
  state: ReturnType<typeof useLivePreferences>;
  /** False for a provider that decides the turns itself: its reflexes are not offered. */
  configurableVad: boolean;
}) {
  const { t } = useTranslation(lng);
  const { preferences, loading, saving, save } = state;
  if (loading || !preferences) return <Skeleton className="h-40 w-full" />;

  const change = async (patch: Partial<LivePreferences>) => {
    const ok = await save(patch);
    if (!ok) toast.error(t('settings.live_mode.preferences_error'));
  };

  return (
    <div className="space-y-4">
      {configurableVad && (
        <div className="flex items-center justify-between gap-4 rounded-lg border bg-card p-3">
          <div className="flex-1 space-y-1">
            <Label htmlFor="live-interruptions">{t('settings.live_mode.interruptions')}</Label>
            <p id="live-interruptions-help" className="text-xs text-muted-foreground">
              {t('settings.live_mode.interruptions_help')}
            </p>
          </div>
          <Switch
            id="live-interruptions"
            aria-describedby="live-interruptions-help"
            checked={preferences.interruptions}
            onCheckedChange={interruptions => void change({ interruptions })}
            disabled={saving}
          />
        </div>
      )}

      {configurableVad && (
        <PreferenceSelect
          id="live-end-of-speech"
          label={t('settings.live_mode.end_of_speech')}
          help={t('settings.live_mode.end_of_speech_help')}
          value={preferences.end_of_speech}
          options={[
            { value: 'calm', label: t('settings.live_mode.end_of_speech_calm') },
            { value: 'normal', label: t('settings.live_mode.end_of_speech_normal') },
            { value: 'lively', label: t('settings.live_mode.end_of_speech_lively') },
          ]}
          disabled={saving}
          onChange={value =>
            void change({ end_of_speech: value as LivePreferences['end_of_speech'] })
          }
        />
      )}
      <PreferenceSelect
        id="live-result-delivery"
        label={t('settings.live_mode.result_delivery')}
        help={t('settings.live_mode.result_delivery_help')}
        value={preferences.result_delivery}
        options={[
          { value: 'interrupt', label: t('settings.live_mode.result_delivery_interrupt') },
          { value: 'when_idle', label: t('settings.live_mode.result_delivery_when_idle') },
        ]}
        disabled={saving}
        onChange={value =>
          void change({ result_delivery: value as LivePreferences['result_delivery'] })
        }
      />
    </div>
  );
}

function PreferenceSelect({
  id,
  label,
  help,
  value,
  options,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  value: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-3">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} aria-describedby={`${id}-help`} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map(option => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p id={`${id}-help`} className="text-xs text-muted-foreground">
        {help}
      </p>
    </div>
  );
}

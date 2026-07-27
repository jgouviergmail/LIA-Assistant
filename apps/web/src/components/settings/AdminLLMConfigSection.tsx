'use client';

import { useEffect, useId, useState } from 'react';
import { toast } from 'sonner';
import {
  Cpu,
  HelpCircle,
  Key,
  Loader2,
  RotateCcw,
  Save,
  Settings2,
  Trash2,
  Eye,
  EyeOff,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useLLMConfig } from '@/hooks/useLLMConfig';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { BaseSettingsProps } from '@/types/settings';
import type {
  LLMTypeConfig,
  LLMTypeConfigUpdate,
  ModelCapabilities,
  OllamaModelsResponse,
  ProviderKeyStatus,
  ReasoningEffortValue,
  VoicesResponse,
} from '@/types/llm-config';
import { LLM_CATEGORIES_ORDER } from '@/types/llm-config';
import { ReasoningWidget } from './llm-config/ReasoningWidget';
import {
  DEFAULT_ELEVENLABS_VOICE_SETTINGS,
  ELEVENLABS_OUTPUT_FORMATS,
  OPENAI_RESPONSE_FORMATS,
  buildConfigUpdate,
  computeAvailableModels,
  findModelCapabilities,
  formAfterModelChange,
  formAfterProviderChange,
  formFromConfig,
  isAnthropicThinkingActive,
  isFieldModified,
  parseProviderConfig,
  resolveTtsProvider,
  samplingVisibility,
  type SamplingVisibility,
  type TTSProviderConfig,
  type TtsProvider,
} from './llm-config/configDialogHelpers';

// --- Reasoning Effort Helpers ---

/** True when the user has set a non-trivial reasoning_effort value, regardless
 * of widget shape. Used to decide whether sampling-param inputs (temp/top_p/
 * penalties) should be hidden on a reasoning-capable model. */
function reasoningEffortIsSet(v: ReasoningEffortValue | null | undefined): boolean {
  if (v === null || v === undefined) return false;
  if ('effort' in v) return true;
  if ('budget' in v && v.budget !== null && v.budget !== undefined) return true;
  if ('enabled' in v && v.enabled) return true;
  return false;
}

/** Compact, human-readable representation of a reasoning_effort value for the
 * tile display. Mirrors the shape of the discriminated union exposed by the
 * backend reasoning_widget. */
function formatReasoningValue(v: ReasoningEffortValue | null | undefined): string {
  if (v === null || v === undefined) return '-';
  if ('effort' in v) return v.effort;
  if ('budget' in v) {
    if (v.budget === 0) return 'off';
    if (v.budget === -1) return 'auto';
    return `${v.budget}t`;
  }
  if ('enabled' in v) {
    if (!v.enabled) return 'off';
    return v.budget != null ? `on/${v.budget}t` : 'on/max';
  }
  return '-';
}

// --- Provider Key Row ---

function ProviderKeyRow({
  provider,
  onUpdate,
  onDelete,
  updating,
  t,
}: {
  provider: ProviderKeyStatus;
  onUpdate: (provider: string, key: string) => Promise<void>;
  onDelete: (provider: string) => Promise<void>;
  updating: boolean;
  t: (key: string) => string;
}) {
  const [editing, setEditing] = useState(false);
  const [keyValue, setKeyValue] = useState('');
  const [showKey, setShowKey] = useState(false);
  const isOllama = provider.provider === 'ollama';

  const handleSave = async () => {
    if (!keyValue.trim()) return;
    try {
      await onUpdate(provider.provider, keyValue.trim());
      setEditing(false);
      setKeyValue('');
      toast.success(t('settings.admin.llmConfig.providers.updated'));
    } catch {
      toast.error(t('settings.admin.llmConfig.providers.error'));
    }
  };

  const handleDelete = async () => {
    try {
      await onDelete(provider.provider);
      toast.success(t('settings.admin.llmConfig.providers.deleted'));
    } catch {
      toast.error(t('settings.admin.llmConfig.providers.error'));
    }
  };

  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div className="flex items-center gap-3">
        <Key className="h-4 w-4 text-muted-foreground" />
        <div>
          <div className="font-medium text-sm">
            {provider.display_name}
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">
              (
              {isOllama
                ? t('settings.admin.llmConfig.providers.baseUrl')
                : t('settings.admin.llmConfig.providers.apiKey')}
              )
            </span>
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            {provider.masked_key && (
              <span className="text-xs text-muted-foreground font-mono">{provider.masked_key}</span>
            )}
            {!provider.has_db_key && (
              <span className="text-xs text-destructive">
                {t('settings.admin.llmConfig.providers.notConfigured')}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {editing ? (
          <>
            <div className="relative">
              <Input
                type={isOllama || showKey ? 'text' : 'password'}
                value={keyValue}
                onChange={e => setKeyValue(e.target.value)}
                placeholder={isOllama ? 'http://localhost:11434/v1' : 'sk-...'}
                className="w-48 pr-8 text-xs"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
            <Button size="sm" onClick={handleSave} disabled={updating || !keyValue.trim()}>
              <Save className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setEditing(false);
                setKeyValue('');
              }}
            >
              {t('common.cancel')}
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              {t('settings.admin.llmConfig.providers.edit')}
            </Button>
            {provider.has_db_key && (
              <Button size="sm" variant="outline" onClick={handleDelete} disabled={updating}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// --- LLM Type Config Card ---

/** Background style per power tier — pastel tints for at-a-glance identification. */
const POWER_TIER_STYLES: Record<string, string> = {
  critical: 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-900/40',
  high: 'bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-900/40',
  medium: 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-900/40',
  low: 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-900/40',
};

function LLMTypeCard({
  config,
  onEdit,
  modelCapabilities,
  t,
}: {
  config: LLMTypeConfig;
  onEdit: (config: LLMTypeConfig) => void;
  /** DB-sourced capabilities for the currently configured model. Sourced
   * from GET /llm-config/metadata; missing when the configured model is
   * not (or no longer) registered. */
  modelCapabilities?: ModelCapabilities;
  t: (key: string) => string;
}) {
  // Use widget + supports_temperature directly (Philosophy A: raw truth).
  // is_reasoning_model alone is ambiguous — deepseek-reasoner is a reasoning
  // model but has widget='none' (always-on, no level control), so it shows
  // neither E: nor T: in the badge.
  const widget = modelCapabilities?.reasoning_widget ?? 'none';
  const hasEffort = widget !== 'none' && reasoningEffortIsSet(config.effective.reasoning_effort);
  const showsTemp = modelCapabilities?.supports_temperature ?? true;
  const tierClass = config.info.power_tier ? (POWER_TIER_STYLES[config.info.power_tier] ?? '') : '';
  return (
    // Real button semantics (audit F012/F013): the whole card opens the edit
    // modal, so it must be reachable and operable with the keyboard. It has
    // no interactive descendants, making role="button" valid here.
    <div
      role="button"
      tabIndex={0}
      className={`rounded-lg border p-3 cursor-pointer hover:brightness-95 dark:hover:brightness-110 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${tierClass}`}
      onClick={() => onEdit(config)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onEdit(config);
        }
      }}
    >
      <div className="flex items-center justify-between mb-0.5">
        <span className="font-medium text-sm">{config.info.display_name}</span>
        {config.is_overridden ? (
          <Badge variant="default" className="text-[10px] px-1.5 py-0">
            {t('settings.admin.llmConfig.types.overridden')}
          </Badge>
        ) : (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
            {t('settings.admin.llmConfig.types.default')}
          </Badge>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground mb-1.5 line-clamp-1">
        {t(config.info.description_key)}
      </p>
      <div className="text-xs text-muted-foreground flex items-center gap-2">
        <span>{config.effective.provider}</span>
        <span className="text-muted-foreground">/</span>
        <span className="font-mono">{config.effective.model}</span>
        <span className="text-muted-foreground">|</span>
        {hasEffort && <span>E:{formatReasoningValue(config.effective.reasoning_effort)}</span>}
        {hasEffort && showsTemp && <span className="text-muted-foreground">+</span>}
        {showsTemp && <span>T:{config.effective.temperature}</span>}
      </div>
    </div>
  );
}

// --- Parameter Tooltip ---

function ParamTooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex ml-1">
      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 rounded-md bg-popover px-3 py-2 text-[11px] text-popover-foreground shadow-md border opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-50 leading-relaxed">
        {text}
      </span>
    </span>
  );
}

// --- Shared dialog field primitives (audit F011) ---

/** Field header: label + optional tooltip + "overridden" badge when modified. */
function OverridableFieldLabel({
  labelKey,
  tooltipKey,
  modified,
  t,
  labelId,
}: {
  labelKey: string;
  tooltipKey?: string;
  modified: boolean;
  t: (key: string) => string;
  /** id set on the visible label so the control can reference it (F012). */
  labelId?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Label id={labelId}>{t(labelKey)}</Label>
      {tooltipKey && <ParamTooltip text={t(tooltipKey)} />}
      {modified && (
        <Badge variant="default" className="text-[10px] px-1 py-0">
          {t('settings.admin.llmConfig.types.overridden')}
        </Badge>
      )}
    </div>
  );
}

/** Labelled range slider with a monospace value display (the four sampling
 * params share this exact layout). */
function RangeParam({
  labelKey,
  tooltipKey,
  modified,
  min,
  max,
  step,
  fallback,
  decimals,
  value,
  onChange,
  t,
}: {
  labelKey: string;
  tooltipKey: string;
  modified: boolean;
  min: number;
  max: number;
  step: number;
  fallback: number;
  decimals: number;
  value: number | null | undefined;
  onChange: (value: number) => void;
  t: (key: string) => string;
}) {
  // Accessible name = the visible label (F012): useId guarantees a unique,
  // stable per-instance id, aria-labelledby makes the association explicit.
  const labelId = useId();
  return (
    <div className="space-y-1.5">
      <OverridableFieldLabel
        labelKey={labelKey}
        tooltipKey={tooltipKey}
        modified={modified}
        t={t}
        labelId={labelId}
      />
      <div className="flex items-center gap-3">
        <input
          type="range"
          aria-labelledby={labelId}
          min={min}
          max={max}
          step={step}
          value={value ?? fallback}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="flex-1"
        />
        <span className="text-sm font-mono w-10 text-right">{value?.toFixed(decimals)}</span>
      </div>
    </div>
  );
}

/** Labelled number input (max_tokens / timeout) — parse semantics stay with
 * the caller via onValueChange(raw). */
function NumberField({
  labelKey,
  tooltipKey,
  modified,
  value,
  placeholder,
  onValueChange,
  t,
}: {
  labelKey: string;
  tooltipKey: string;
  modified: boolean;
  value: number | null | undefined;
  placeholder?: string;
  onValueChange: (raw: string) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-1.5">
      <OverridableFieldLabel
        labelKey={labelKey}
        tooltipKey={tooltipKey}
        modified={modified}
        t={t}
      />
      <Input
        type="number"
        min="1"
        value={value ?? ''}
        onChange={e => onValueChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

// --- TTS Provider-specific configuration block ---

/** Voice picker: catalogue select when the live/static list is available,
 * free-text voice-id input otherwise. */
function TtsVoicePicker({
  labelKey,
  value,
  options,
  loading,
  onChange,
  t,
}: {
  labelKey: string;
  value: string;
  options: VoicesResponse['voices'];
  loading: boolean;
  onChange: (voiceId: string) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{t(labelKey)}</Label>
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-1.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {t('settings.admin.llmConfig.voiceTts.loadingVoices')}
        </div>
      ) : options.length > 0 ? (
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder={t('settings.admin.llmConfig.voiceTts.pickVoice')} />
          </SelectTrigger>
          <SelectContent>
            {options.map(o => (
              <SelectItem key={o.voice_id} value={o.voice_id}>
                {o.label}
                {o.language ? ` · ${o.language}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={t('settings.admin.llmConfig.voiceTts.voiceIdPlaceholder')}
        />
      )}
    </div>
  );
}

type SetTtsKey = <K extends keyof TTSProviderConfig>(key: K, value: TTSProviderConfig[K]) => void;

/** Edge — SSML rate / pitch / volume strings (e.g. "+10%", "-2Hz"). */
function EdgeTuning({
  providerConfig,
  setKey,
  t,
}: {
  providerConfig: TTSProviderConfig;
  setKey: SetTtsKey;
  t: (key: string) => string;
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="space-y-1.5">
        <Label className="text-xs">{t('settings.admin.llmConfig.voiceTts.rate')}</Label>
        <Input
          value={providerConfig.rate ?? ''}
          onChange={e => setKey('rate', e.target.value)}
          placeholder="+10%"
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{t('settings.admin.llmConfig.voiceTts.pitch')}</Label>
        <Input
          value={providerConfig.pitch ?? ''}
          onChange={e => setKey('pitch', e.target.value)}
          placeholder="+0Hz"
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{t('settings.admin.llmConfig.voiceTts.volume')}</Label>
        <Input
          value={providerConfig.volume ?? ''}
          onChange={e => setKey('volume', e.target.value)}
          placeholder="+0%"
        />
      </div>
    </div>
  );
}

/** OpenAI — speed (0.25..4.0) + response audio container format. */
function OpenAITuning({
  providerConfig,
  setKey,
  t,
}: {
  providerConfig: TTSProviderConfig;
  setKey: SetTtsKey;
  t: (key: string) => string;
}) {
  // Accessible name for the speed slider = its visible label (F012).
  const speedLabelId = useId();
  return (
    <>
      <div className="space-y-1.5">
        <Label id={speedLabelId}>{t('settings.admin.llmConfig.voiceTts.speed')}</Label>
        <div className="flex items-center gap-3">
          <input
            type="range"
            aria-labelledby={speedLabelId}
            min="0.25"
            max="4"
            step="0.05"
            value={providerConfig.speed ?? 1.0}
            onChange={e => setKey('speed', parseFloat(e.target.value))}
            className="flex-1"
          />
          <span className="text-sm font-mono w-12 text-right">
            {(providerConfig.speed ?? 1.0).toFixed(2)}x
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>{t('settings.admin.llmConfig.voiceTts.responseFormat')}</Label>
        <Select
          value={providerConfig.response_format ?? 'mp3'}
          onValueChange={v => setKey('response_format', v)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OPENAI_RESPONSE_FORMATS.map(f => (
              <SelectItem key={f} value={f}>
                {f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  );
}

/** One ElevenLabs voice_settings slider (stability / similarity / style share
 * the exact 0..1 step-0.05 layout with a 2-decimal display). */
function VoiceSettingSlider({
  labelKey,
  value,
  onChange,
  t,
}: {
  labelKey: string;
  value: number;
  onChange: (value: number) => void;
  t: (key: string) => string;
}) {
  // Accessible name = the visible label (F012), unique per instance.
  const labelId = useId();
  return (
    <div className="space-y-1.5">
      <Label id={labelId}>{t(labelKey)}</Label>
      <div className="flex items-center gap-3">
        <input
          type="range"
          aria-labelledby={labelId}
          min="0"
          max="1"
          step="0.05"
          value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="flex-1"
        />
        <span className="text-sm font-mono w-12 text-right">{value.toFixed(2)}</span>
      </div>
    </div>
  );
}

/** ElevenLabs — output container + voice_settings (stability/similarity/style). */
function ElevenLabsTuning({
  providerConfig,
  setKey,
  setVoiceSetting,
  t,
}: {
  providerConfig: TTSProviderConfig;
  setKey: SetTtsKey;
  setVoiceSetting: <K extends keyof NonNullable<TTSProviderConfig['voice_settings']>>(
    key: K,
    value: NonNullable<TTSProviderConfig['voice_settings']>[K]
  ) => void;
  t: (key: string) => string;
}) {
  const settings = providerConfig.voice_settings;
  // Speaker-boost checkbox: explicit label association (F012); htmlFor
  // gives native label-click toggling as a bonus.
  const boostLabelId = useId();
  const boostInputId = useId();
  return (
    <>
      <div className="space-y-1.5">
        <Label>{t('settings.admin.llmConfig.voiceTts.outputFormat')}</Label>
        <Select
          value={providerConfig.output_format ?? 'mp3_44100_128'}
          onValueChange={v => setKey('output_format', v)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ELEVENLABS_OUTPUT_FORMATS.map(f => (
              <SelectItem key={f} value={f}>
                {f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <VoiceSettingSlider
        labelKey="settings.admin.llmConfig.voiceTts.stability"
        value={settings?.stability ?? DEFAULT_ELEVENLABS_VOICE_SETTINGS.stability}
        onChange={v => setVoiceSetting('stability', v)}
        t={t}
      />
      <VoiceSettingSlider
        labelKey="settings.admin.llmConfig.voiceTts.similarityBoost"
        value={settings?.similarity_boost ?? DEFAULT_ELEVENLABS_VOICE_SETTINGS.similarity_boost}
        onChange={v => setVoiceSetting('similarity_boost', v)}
        t={t}
      />
      <VoiceSettingSlider
        labelKey="settings.admin.llmConfig.voiceTts.style"
        value={settings?.style ?? DEFAULT_ELEVENLABS_VOICE_SETTINGS.style}
        onChange={v => setVoiceSetting('style', v)}
        t={t}
      />
      <div className="flex items-center justify-between">
        <Label id={boostLabelId} htmlFor={boostInputId} className="text-sm">
          {t('settings.admin.llmConfig.voiceTts.useSpeakerBoost')}
        </Label>
        <input
          id={boostInputId}
          type="checkbox"
          aria-labelledby={boostLabelId}
          checked={
            settings?.use_speaker_boost ?? DEFAULT_ELEVENLABS_VOICE_SETTINGS.use_speaker_boost
          }
          onChange={e => setVoiceSetting('use_speaker_boost', e.target.checked)}
          className="h-4 w-4"
        />
      </div>
    </>
  );
}

/** Renders the voice pickers (male / female) plus provider-specific tuning
 * inputs for the voice_tts LLM type. Bound to a parsed ``provider_config``
 * object exposed by the parent dialog; serialisation back to JSONB happens
 * only at save time so the form can stay schema-aware. */
function TTSProviderConfigBlock({
  provider,
  providerConfig,
  setProviderConfig,
  voicesData,
  voicesLoading,
  t,
}: {
  provider: TtsProvider;
  providerConfig: TTSProviderConfig;
  setProviderConfig: React.Dispatch<React.SetStateAction<TTSProviderConfig>>;
  voicesData: VoicesResponse | null;
  voicesLoading: boolean;
  t: (key: string) => string;
}) {
  const setKey: SetTtsKey = (key, value) => setProviderConfig(prev => ({ ...prev, [key]: value }));

  const setVoiceSetting = <K extends keyof NonNullable<TTSProviderConfig['voice_settings']>>(
    key: K,
    value: NonNullable<TTSProviderConfig['voice_settings']>[K]
  ) =>
    setProviderConfig(prev => ({
      ...prev,
      voice_settings: {
        ...DEFAULT_ELEVENLABS_VOICE_SETTINGS,
        ...prev.voice_settings,
        [key]: value,
      },
    }));

  // Filter the live voice catalogue by gender so the male / female
  // dropdowns each show only relevant entries; gender-less voices are
  // appended to both pickers (e.g. OpenAI's "alloy"/"fable").
  const voices = voicesData?.voices ?? [];
  const maleVoices = voices.filter(v => v.gender === 'male' || v.gender === null);
  const femaleVoices = voices.filter(v => v.gender === 'female' || v.gender === null);

  return (
    <div className="space-y-4 rounded-md border p-3 bg-muted/20">
      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {t('settings.admin.llmConfig.voiceTts.sectionTitle')}
      </div>

      <TtsVoicePicker
        labelKey="settings.admin.llmConfig.voiceTts.voiceMale"
        value={providerConfig.voice_male ?? ''}
        options={maleVoices}
        loading={voicesLoading}
        onChange={v => setKey('voice_male', v)}
        t={t}
      />
      <TtsVoicePicker
        labelKey="settings.admin.llmConfig.voiceTts.voiceFemale"
        value={providerConfig.voice_female ?? ''}
        options={femaleVoices}
        loading={voicesLoading}
        onChange={v => setKey('voice_female', v)}
        t={t}
      />

      {provider === 'edge' && <EdgeTuning providerConfig={providerConfig} setKey={setKey} t={t} />}
      {provider === 'openai' && (
        <OpenAITuning providerConfig={providerConfig} setKey={setKey} t={t} />
      )}
      {provider === 'elevenlabs' && (
        <ElevenLabsTuning
          providerConfig={providerConfig}
          setKey={setKey}
          setVoiceSetting={setVoiceSetting}
          t={t}
        />
      )}

      {voicesData?.source === 'live' && provider === 'elevenlabs' && (
        <p className="text-[11px] text-emerald-500">
          {t('settings.admin.llmConfig.voiceTts.liveCatalogue')}
        </p>
      )}
    </div>
  );
}

// --- Edit Dialog ---

/** Provider selector: only providers exposing at least one model matching the
 * LLM type's required_kind are proposed. Switching wipes model +
 * reasoning_effort (+ the TTS tuning, which is provider-scoped). */
function ProviderField({
  form,
  metadataProviders,
  requiredKind,
  modified,
  onProviderChange,
  t,
}: {
  form: LLMTypeConfigUpdate;
  metadataProviders: Record<string, ModelCapabilities[]>;
  requiredKind: LLMTypeConfig['info']['required_kind'];
  modified: boolean;
  onProviderChange: (provider: string) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-1.5">
      <OverridableFieldLabel
        labelKey="settings.admin.llmConfig.fields.provider"
        modified={modified}
        t={t}
      />
      <Select value={form.provider ?? ''} onValueChange={onProviderChange}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(metadataProviders)
            // Only show providers that actually expose at least one
            // model matching the LLM type's required_kind. Avoids
            // proposing ``openai`` for voice_transcription when the
            // catalogue has no kind=audio model under it (and inversely).
            .filter(([, models]) => models.some(m => m.kind === requiredKind))
            .map(([p]) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Model selector: live Ollama spinner → catalogue select → "no compatible
 * model" notice → free-text input, plus the Ollama live/fallback source note. */
function ModelField({
  form,
  availableModels,
  requiredCaps,
  ollamaLoading,
  ollamaData,
  modified,
  onModelChange,
  onFreeTextModel,
  t,
}: {
  form: LLMTypeConfigUpdate;
  availableModels: string[];
  requiredCaps: string[];
  ollamaLoading: boolean;
  ollamaData: OllamaModelsResponse | null;
  modified: boolean;
  onModelChange: (modelId: string) => void;
  onFreeTextModel: (raw: string) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-1.5">
      <OverridableFieldLabel
        labelKey="settings.admin.llmConfig.fields.model"
        modified={modified}
        t={t}
      />
      {form.provider === 'ollama' && ollamaLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-1.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {t('settings.admin.llmConfig.ollama.loading')}
        </div>
      ) : availableModels.length > 0 ? (
        <Select value={form.model ?? ''} onValueChange={onModelChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {availableModels.map(m => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : requiredCaps.length > 0 && form.provider ? (
        <p className="text-sm text-muted-foreground italic">
          {t('settings.admin.llmConfig.no_compatible_model')}
        </p>
      ) : (
        <Input
          value={form.model ?? ''}
          onChange={e => onFreeTextModel(e.target.value)}
          placeholder="model-name"
        />
      )}
      {form.provider === 'ollama' && !ollamaLoading && ollamaData && (
        <p
          className={`text-[11px] mt-1 ${ollamaData.source === 'live' ? 'text-emerald-500' : 'text-amber-500'}`}
        >
          {ollamaData.source === 'live'
            ? t('settings.admin.llmConfig.ollama.live')
            : t('settings.admin.llmConfig.ollama.fallback')}
        </p>
      )}
    </div>
  );
}

/** Reasoning-effort widget (+ Anthropic sampling-constraint note) and the
 * separate global 'effort' selector for models that declare effort_values. */
function ReasoningSection({
  form,
  caps,
  anthropicThinkingActive,
  isModified,
  onReasoningChange,
  onEffortChange,
  t,
}: {
  form: LLMTypeConfigUpdate;
  caps: ModelCapabilities | undefined;
  anthropicThinkingActive: boolean;
  isModified: (field: keyof LLMTypeConfigUpdate) => boolean;
  onReasoningChange: (next: ReasoningEffortValue) => void;
  onEffortChange: (effort: string | null) => void;
  t: (key: string) => string;
}) {
  return (
    <>
      {/* Reasoning Effort — driven by ModelCapabilities.reasoning_widget.
          The widget renders nothing when widget='none', so no outer guard
          is needed. */}
      {form.provider && form.model && caps && (
        <div className="space-y-1.5">
          <OverridableFieldLabel
            labelKey="settings.admin.llmConfig.fields.reasoningEffort"
            tooltipKey="settings.admin.llmConfig.tooltips.reasoningEffort"
            modified={isModified('reasoning_effort')}
            t={t}
          />
          <ReasoningWidget
            widget={caps.reasoning_widget ?? 'none'}
            enumValues={caps.reasoning_enum_values}
            budgetRange={caps.reasoning_budget_range}
            docI18nKey={caps.reasoning_doc_i18n_key}
            value={form.reasoning_effort ?? null}
            onChange={onReasoningChange}
          />
          {anthropicThinkingActive && (
            <p className="text-xs text-muted-foreground">
              {t('settings.admin.llmConfig.constraints.reasoningTemp')}
            </p>
          )}
        </div>
      )}

      {/* Global 'effort' (Anthropic output_config.effort) — a separate
          token-spend control, distinct from reasoning_effort. Shown only when
          the model declares effort_values (currently opus-4-5). */}
      {caps?.effort_values && caps.effort_values.length > 0 && (
        <div className="space-y-1.5">
          <OverridableFieldLabel
            labelKey="settings.admin.llmConfig.fields.effort"
            tooltipKey="settings.admin.llmConfig.tooltips.effort"
            modified={isModified('effort')}
            t={t}
          />
          <Select
            value={form.effort ?? '__default__'}
            onValueChange={v => onEffortChange(v === '__default__' ? null : v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__default__">
                {t('settings.admin.llmConfig.fields.reasoningDefault')}
              </SelectItem>
              {caps.effort_values.map(ev => (
                <SelectItem key={ev} value={ev}>
                  {ev}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </>
  );
}

/** Dialog-side dynamic catalogues: live Ollama models (fetched only while the
 * Ollama provider is selected) and the TTS voice catalogue (fetched only for
 * TTS types on a supported provider — any other provider keeps voicesData
 * null). */
function useLlmDialogQueries(
  config: LLMTypeConfig | null,
  form: LLMTypeConfigUpdate,
  open: boolean
) {
  // Dynamic Ollama model discovery: fetch only when Ollama is selected
  const { data: ollamaData, loading: ollamaLoading } = useApiQuery<OllamaModelsResponse>(
    '/admin/llm-config/providers/ollama/models',
    {
      componentName: 'LLMConfigDialog',
      initialData: { models: [], source: 'fallback' as const },
      enabled: form.provider === 'ollama' && open,
      deps: [form.provider, open],
    }
  );

  // Dynamic voice catalogue for TTS LLM types. Edge / OpenAI return curated
  // static lists; ElevenLabs triggers a live ``GET /v1/voices`` against the
  // configured account (account-scoped custom + shared voices).
  const isTts = config?.info.required_kind === 'tts';
  const ttsProvider = resolveTtsProvider(isTts, form.provider);
  const { data: voicesData, loading: voicesLoading } = useApiQuery<VoicesResponse>(
    `/admin/voice/voices?provider=${ttsProvider ?? 'edge'}`,
    {
      componentName: 'LLMConfigDialog',
      enabled: !!ttsProvider && open,
      deps: [ttsProvider, open],
    }
  );

  return {
    ollamaData: ollamaData ?? null,
    ollamaLoading,
    ollamaModels: ollamaData?.models ?? [],
    isTts,
    ttsProvider,
    voicesData: voicesData ?? null,
    voicesLoading,
  };
}

/** The six tunable execution params, in their historical display order:
 * temperature, max_tokens, top_p, frequency/presence penalties, timeout.
 * Slider visibility is model-capability driven. */
function SamplingFields({
  form,
  setForm,
  visibility,
  isModified,
  t,
}: {
  form: LLMTypeConfigUpdate;
  setForm: (form: LLMTypeConfigUpdate) => void;
  visibility: SamplingVisibility;
  isModified: (field: keyof LLMTypeConfigUpdate) => boolean;
  t: (key: string) => string;
}) {
  return (
    <>
      {/* Temperature — shown only if the model accepts it (DB-driven). */}
      {visibility.showTemperature && (
        <RangeParam
          labelKey="settings.admin.llmConfig.fields.temperature"
          tooltipKey="settings.admin.llmConfig.tooltips.temperature"
          modified={isModified('temperature')}
          min={0}
          max={2}
          step={0.1}
          fallback={0}
          decimals={1}
          value={form.temperature}
          onChange={v => setForm({ ...form, temperature: v })}
          t={t}
        />
      )}

      <NumberField
        labelKey="settings.admin.llmConfig.fields.maxTokens"
        tooltipKey="settings.admin.llmConfig.tooltips.maxTokens"
        modified={isModified('max_tokens')}
        value={form.max_tokens}
        onValueChange={raw => setForm({ ...form, max_tokens: parseInt(raw) || null })}
        t={t}
      />

      {/* Top P — shown only if the model accepts it (DB-driven). */}
      {visibility.showTopP && (
        <RangeParam
          labelKey="settings.admin.llmConfig.fields.topP"
          tooltipKey="settings.admin.llmConfig.tooltips.topP"
          modified={isModified('top_p')}
          min={0}
          max={1}
          step={0.05}
          fallback={1}
          decimals={2}
          value={form.top_p}
          onChange={v => setForm({ ...form, top_p: v })}
          t={t}
        />
      )}

      {/* Frequency Penalty — shown only if the model accepts it (DB-driven). */}
      {visibility.showFrequencyPenalty && (
        <RangeParam
          labelKey="settings.admin.llmConfig.fields.frequencyPenalty"
          tooltipKey="settings.admin.llmConfig.tooltips.frequencyPenalty"
          modified={isModified('frequency_penalty')}
          min={-2}
          max={2}
          step={0.1}
          fallback={0}
          decimals={1}
          value={form.frequency_penalty}
          onChange={v => setForm({ ...form, frequency_penalty: v })}
          t={t}
        />
      )}

      {/* Presence Penalty — shown only if the model accepts it (DB-driven). */}
      {visibility.showPresencePenalty && (
        <RangeParam
          labelKey="settings.admin.llmConfig.fields.presencePenalty"
          tooltipKey="settings.admin.llmConfig.tooltips.presencePenalty"
          modified={isModified('presence_penalty')}
          min={-2}
          max={2}
          step={0.1}
          fallback={0}
          decimals={1}
          value={form.presence_penalty}
          onChange={v => setForm({ ...form, presence_penalty: v })}
          t={t}
        />
      )}

      <NumberField
        labelKey="settings.admin.llmConfig.fields.timeout"
        tooltipKey="settings.admin.llmConfig.tooltips.timeout"
        modified={isModified('timeout_seconds')}
        value={form.timeout_seconds}
        placeholder={t('settings.admin.llmConfig.fields.timeoutPlaceholder')}
        onValueChange={raw => setForm({ ...form, timeout_seconds: raw ? parseInt(raw) : null })}
        t={t}
      />
    </>
  );
}

function LLMConfigDialog({
  config,
  open,
  onClose,
  onSave,
  onReset,
  saving,
  metadata,
  t,
}: {
  config: LLMTypeConfig | null;
  open: boolean;
  onClose: () => void;
  onSave: (llmType: string, data: LLMTypeConfigUpdate) => Promise<LLMTypeConfig | undefined>;
  onReset: (llmType: string) => Promise<LLMTypeConfig | undefined>;
  saving: boolean;
  metadata: {
    providers: Record<string, ModelCapabilities[]>;
  };
  t: (key: string) => string;
}) {
  const [form, setForm] = useState<LLMTypeConfigUpdate>({});
  // Parsed ``provider_config`` JSONB blob — only consumed when the LLM type's
  // required_kind is ``tts``. Stored as an object so the form can bind to
  // nested fields (e.g. ``voice_settings.stability``); serialised back to a
  // JSON string in handleSave().
  const [providerConfig, setProviderConfig] = useState<TTSProviderConfig>({});

  // Populate form when config changes (proper useEffect instead of render-time setState)
  useEffect(() => {
    if (config && open) {
      setForm(formFromConfig(config));
      setProviderConfig(parseProviderConfig(config.effective.provider_config));
    }
  }, [config, open]);

  const handleClose = () => {
    setForm({});
    setProviderConfig({});
    onClose();
  };

  const handleSave = async () => {
    if (!config) return;
    // Build update: compare with defaults, send null for unchanged fields
    const update = buildConfigUpdate(config, form, providerConfig);
    try {
      await onSave(config.llm_type, update);
      toast.success(t('settings.admin.llmConfig.config.saved'));
      handleClose();
    } catch {
      toast.error(t('settings.admin.llmConfig.config.error'));
    }
  };

  const handleReset = async () => {
    if (!config) return;
    try {
      await onReset(config.llm_type);
      toast.success(t('settings.admin.llmConfig.config.reset'));
      handleClose();
    } catch {
      toast.error(t('settings.admin.llmConfig.config.error'));
    }
  };

  const { ollamaData, ollamaLoading, ollamaModels, isTts, ttsProvider, voicesData, voicesLoading } =
    useLlmDialogQueries(config, form, open);

  // Filter models by required_kind + required_capabilities from LLM type config.
  const requiredCaps = config?.info.required_capabilities ?? [];
  const requiredKind = config?.info.required_kind ?? 'chat';
  const availableModels = computeAvailableModels(
    form.provider,
    metadata.providers,
    ollamaModels,
    requiredKind,
    requiredCaps
  );
  const selectedModelCapabilities = (metadata.providers[form.provider ?? ''] ?? []).find(
    m => m.model_id === form.model
  );
  const anthropicThinkingActive = isAnthropicThinkingActive(form.provider, form.reasoning_effort);
  const visibility: SamplingVisibility = samplingVisibility(
    selectedModelCapabilities,
    anthropicThinkingActive
  );
  const isModified = (field: keyof LLMTypeConfigUpdate) =>
    config ? isFieldModified(config, form, field) : false;

  const handleProviderChange = (provider: string) => {
    setForm(formAfterProviderChange(form, provider));
    // Voice IDs and per-provider tuning are provider-scoped — wipe
    // them so the admin can't accidentally save a stale Edge
    // voice_id under an OpenAI override (would crash at synth).
    if (isTts) setProviderConfig({});
  };

  const handleModelChange = (modelId: string) => {
    const newCaps = findModelCapabilities(metadata.providers, ollamaModels, form.provider, modelId);
    setForm(formAfterModelChange(form, modelId, newCaps));
  };

  const handleReasoningChange = (next: ReasoningEffortValue) => {
    // Enabling Anthropic thinking forces temperature/top_p off
    // (API constraint) — clear them so the saved config is coherent.
    const willThink = isAnthropicThinkingActive(form.provider, next);
    setForm({
      ...form,
      reasoning_effort: next,
      ...(willThink ? { temperature: null, top_p: null } : {}),
    });
  };

  if (!config) return null;

  return (
    <Dialog open={open} onOpenChange={o => !o && handleClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            {config.info.display_name}
          </DialogTitle>
          <DialogDescription>{t(config.info.description_key)}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2 max-h-[60dvh] overflow-y-auto pr-1">
          <ProviderField
            form={form}
            metadataProviders={metadata.providers}
            requiredKind={requiredKind}
            modified={isModified('provider')}
            onProviderChange={handleProviderChange}
            t={t}
          />

          <ModelField
            form={form}
            availableModels={availableModels}
            requiredCaps={requiredCaps}
            ollamaLoading={ollamaLoading}
            ollamaData={ollamaData}
            modified={isModified('model')}
            onModelChange={handleModelChange}
            onFreeTextModel={raw =>
              // Free-typed model name (e.g. a dynamic Ollama model): its
              // reasoning widget is unknown here, so we cannot keep any
              // reasoning_effort override — clear it to null (= model default).
              setForm({ ...form, model: raw, reasoning_effort: null })
            }
            t={t}
          />

          {/* Voice TTS — voice picker + provider-specific tuning. Rendered
              only for the voice_tts LLM type (kind=tts). The voice_id and
              tuning live inside ``provider_config`` JSONB so the per-model
              defaults and overrides survive a provider switch. */}
          {isTts && ttsProvider && (
            <TTSProviderConfigBlock
              provider={ttsProvider}
              providerConfig={providerConfig}
              setProviderConfig={setProviderConfig}
              voicesData={voicesData}
              voicesLoading={voicesLoading}
              t={t}
            />
          )}

          <SamplingFields
            form={form}
            setForm={setForm}
            visibility={visibility}
            isModified={isModified}
            t={t}
          />

          <ReasoningSection
            form={form}
            caps={selectedModelCapabilities}
            anthropicThinkingActive={anthropicThinkingActive}
            isModified={isModified}
            onReasoningChange={handleReasoningChange}
            onEffortChange={effort => setForm({ ...form, effort })}
            t={t}
          />
        </div>

        <DialogFooter className="flex justify-between sm:justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={saving || !config.is_overridden}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            {t('settings.admin.llmConfig.config.resetButton')}
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleClose}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {t('common.save')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Main Component ---

export default function AdminLLMConfigSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const {
    configs,
    providers,
    metadata,
    loading,
    updatingConfig,
    updatingKey,
    updateConfig,
    resetConfig,
    updateProviderKey,
    deleteProviderKey,
  } = useLLMConfig();

  const [editingConfig, setEditingConfig] = useState<LLMTypeConfig | null>(null);

  // Group configs by category
  const configsByCategory = LLM_CATEGORIES_ORDER.reduce(
    (acc, cat) => {
      acc[cat] = configs.filter(c => c.info.category === cat);
      return acc;
    },
    {} as Record<string, LLMTypeConfig[]>
  );

  // Only show loading spinner on initial load, not during refetches
  // (refetches set loading=true which would unmount the entire content and cause focus loss)
  const content =
    loading && configs.length === 0 ? (
      <div className="animate-pulse text-sm text-muted-foreground">{t('common.loading')}</div>
    ) : (
      <div className="space-y-8">
        {/* Provider Keys Section */}
        <div>
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Key className="h-4 w-4" />
            {t('settings.admin.llmConfig.providers.title')}
          </h3>
          <p className="text-xs text-muted-foreground mb-3">
            {t('settings.admin.llmConfig.providers.description')}
          </p>
          <div className="space-y-2">
            {providers.map(p => (
              <ProviderKeyRow
                key={p.provider}
                provider={p}
                onUpdate={updateProviderKey}
                onDelete={deleteProviderKey}
                updating={updatingKey}
                t={t}
              />
            ))}
          </div>
        </div>

        {/* LLM Types Section */}
        <div>
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Cpu className="h-4 w-4" />
            {t('settings.admin.llmConfig.types.title')}
          </h3>
          <p className="text-xs text-muted-foreground mb-4">
            {t('settings.admin.llmConfig.types.description')}
          </p>

          {LLM_CATEGORIES_ORDER.map(cat => {
            const catConfigs = configsByCategory[cat];
            if (!catConfigs?.length) return null;

            return (
              <div key={cat} className="mb-6">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  {t(`settings.admin.llmConfig.categories.${cat}`)}
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {catConfigs.map(c => {
                    const modelCapabilities = (metadata.providers[c.effective.provider] ?? []).find(
                      m => m.model_id === c.effective.model
                    );
                    return (
                      <LLMTypeCard
                        key={c.llm_type}
                        config={c}
                        onEdit={setEditingConfig}
                        modelCapabilities={modelCapabilities}
                        t={t}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* Edit Dialog */}
        <LLMConfigDialog
          config={editingConfig}
          open={!!editingConfig}
          onClose={() => setEditingConfig(null)}
          onSave={updateConfig}
          onReset={resetConfig}
          saving={updatingConfig}
          metadata={metadata}
          t={t}
        />
      </div>
    );

  return (
    <SettingsSection
      value="admin-llm-config"
      title={t('settings.admin.llmConfig.title')}
      description={t('settings.admin.llmConfig.description')}
      icon={Cpu}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}

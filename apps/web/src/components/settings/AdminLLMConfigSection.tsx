'use client';

import { useEffect, useState } from 'react';
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
  OllamaModelsResponse,
  ProviderKeyStatus,
  ReasoningEffort,
} from '@/types/llm-config';
import { LLM_CATEGORIES_ORDER } from '@/types/llm-config';

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

function LLMTypeCard({
  config,
  onEdit,
  t,
}: {
  config: LLMTypeConfig;
  onEdit: (config: LLMTypeConfig) => void;
  t: (key: string) => string;
}) {
  const tileConstraints = getModelConstraints(
    config.effective.provider,
    config.effective.model,
    config.effective.reasoning_effort
  );
  return (
    <div
      className="rounded-lg border p-3 cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={() => onEdit(config)}
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
      <p className="text-[11px] text-muted-foreground/70 mb-1.5 line-clamp-1">
        {t(config.info.description_key)}
      </p>
      <div className="text-xs text-muted-foreground flex items-center gap-2">
        <span>{config.effective.provider}</span>
        <span className="text-muted-foreground/50">/</span>
        <span className="font-mono">{config.effective.model}</span>
        <span className="text-muted-foreground/50">|</span>
        <span>
          {tileConstraints.isReasoningModel
            ? `E:${config.effective.reasoning_effort ?? '-'}`
            : `T:${config.effective.temperature}`}
        </span>
        {tileConstraints.isReasoningModel && tileConstraints.supportsTemperature && (
          <>
            <span className="text-muted-foreground/50">+</span>
            <span>T:{config.effective.temperature}</span>
          </>
        )}
      </div>
    </div>
  );
}

// --- Model Constraints Helper ---

/** Parameter support constraints per provider/model family.
 * Based on official API documentation for each provider (2026-03). */
interface ModelConstraints {
  supportsTemperature: boolean;
  supportsTopP: boolean;
  supportsFrequencyPenalty: boolean;
  supportsPresencePenalty: boolean;
  supportsReasoningEffort: boolean;
  isReasoningModel: boolean;
  /** Max temperature value (1.0 for Anthropic, 2.0 for others) */
  temperatureMax: number;
  /** Available reasoning_effort values for the dropdown */
  reasoningEffortOptions: string[];
  /** Warning message key if temperature is forced/restricted */
  temperatureWarning: string | null;
}

const OPENAI_REASONING_PATTERN = /^(o[0-9](-.*)?|gpt-5([.-].*)?)$/i;
const OPENAI_O1_MINI_PATTERN = /^o1-mini/i;

function getModelConstraints(
  provider: string,
  model: string,
  reasoningEffort?: string | null
): ModelConstraints {
  const defaults: ModelConstraints = {
    supportsTemperature: true,
    supportsTopP: true,
    supportsFrequencyPenalty: true,
    supportsPresencePenalty: true,
    supportsReasoningEffort: false,
    isReasoningModel: false,
    temperatureMax: 2.0,
    reasoningEffortOptions: [],
    temperatureWarning: null,
  };

  if (!provider || !model) return defaults;

  switch (provider) {
    case 'openai': {
      const isReasoning = OPENAI_REASONING_PATTERN.test(model);
      if (!isReasoning) return defaults;

      // All OpenAI reasoning models: no temperature, top_p, frequency/presence_penalty
      const isO1Mini = OPENAI_O1_MINI_PATTERN.test(model);
      const isOSeries = /^o[0-9]/i.test(model);
      const isGPT52 = /^gpt-5\.2/i.test(model);
      const isGPT51 = /^gpt-5\.1/i.test(model);
      const isGPT5X = /^gpt-5\.\d/i.test(model);

      let reasoningOptions: string[];
      if (isO1Mini) {
        // o1-mini: no reasoning_effort support
        reasoningOptions = [];
      } else if (isGPT52) {
        reasoningOptions = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh'];
      } else if (isGPT51) {
        // effort="none" disables reasoning on gpt-5.1 (makes sampling params available at API level)
        reasoningOptions = ['none', 'low', 'medium', 'high'];
      } else if (isOSeries) {
        // o1, o3, o3-mini, o4-mini
        reasoningOptions = ['low', 'medium', 'high'];
      } else if (isGPT5X) {
        // Future gpt-5.X models: conservative
        reasoningOptions = ['low', 'medium', 'high'];
      } else {
        // gpt-5, gpt-5-mini
        reasoningOptions = ['minimal', 'low', 'medium', 'high'];
      }

      // gpt-5.1/5.2+ with effort=none: reasoning disabled, sampling params available
      if ((isGPT51 || isGPT52) && reasoningEffort === 'none') {
        return {
          supportsTemperature: true,
          supportsTopP: true,
          supportsFrequencyPenalty: false, // Never supported on reasoning model family
          supportsPresencePenalty: false,
          supportsReasoningEffort: true,
          isReasoningModel: true,
          temperatureMax: 2.0,
          reasoningEffortOptions: reasoningOptions,
          temperatureWarning: null,
        };
      }

      return {
        supportsTemperature: false,
        supportsTopP: false,
        supportsFrequencyPenalty: false,
        supportsPresencePenalty: false,
        supportsReasoningEffort: !isO1Mini,
        isReasoningModel: true,
        temperatureMax: 2.0,
        reasoningEffortOptions: reasoningOptions,
        temperatureWarning: 'settings.admin.llmConfig.constraints.reasoningTemp',
      };
    }

    case 'perplexity':
      // Perplexity: temperature, top_p, frequency_penalty and presence_penalty all supported
      // (OpenAI-compatible API; note: freq_penalty uses multiplicative range 1.0–2.0 on Perplexity side)
      return defaults;

    case 'anthropic': {
      // Anthropic: temperature max 1.0, NO frequency/presence penalty
      // top_p supported but mutually exclusive with temperature (handled by adapter)
      // Effort (extended thinking): only claude-3-7-sonnet+ and claude-4.x support it
      // claude-3-5-sonnet does NOT support extended thinking
      const supportsThinking = !model || !/^claude-3-5/i.test(model);
      return {
        ...defaults,
        supportsTopP: false, // Hide to avoid temp+top_p conflict
        supportsFrequencyPenalty: false,
        supportsPresencePenalty: false,
        supportsReasoningEffort: supportsThinking,
        temperatureMax: 1.0,
        reasoningEffortOptions: supportsThinking ? ['low', 'medium', 'high'] : [],
      };
    }

    case 'gemini': {
      // Gemini: no frequency/presence penalty
      // Thinking via thinking_level mapped from reasoning_effort
      // Only Gemini 2.5-flash, 2.5-pro, and 3+ support thinking
      // Gemini 2.0-flash, 2.0-flash-lite, 2.5-flash-lite do NOT
      const supportsGeminiThinking =
        /^gemini-(2\.5-(flash|pro)|[3-9])/i.test(model) && !/lite/i.test(model);
      return {
        ...defaults,
        supportsFrequencyPenalty: false,
        supportsPresencePenalty: false,
        supportsReasoningEffort: supportsGeminiThinking,
        reasoningEffortOptions: supportsGeminiThinking ? ['low', 'medium', 'high'] : [],
      };
    }

    case 'deepseek': {
      // deepseek-reasoner (R1): no sampling parameters supported — API rejects them
      const isReasoner = /^deepseek-reasoner/i.test(model);
      if (isReasoner) {
        return {
          ...defaults,
          supportsTemperature: false,
          supportsTopP: false,
          supportsFrequencyPenalty: false,
          supportsPresencePenalty: false,
          isReasoningModel: true,
          temperatureWarning: 'settings.admin.llmConfig.constraints.reasoningTemp',
        };
      }
      // deepseek-chat (V3): all standard params supported
      return defaults;
    }

    case 'qwen': {
      // Qwen: no frequency_penalty, supports thinking via enable_thinking
      // All 3 models (qwen3-max, qwen3.5-plus, qwen3.5-flash) support thinking
      return {
        ...defaults,
        supportsFrequencyPenalty: false,
        supportsReasoningEffort: true,
        reasoningEffortOptions: ['none', 'low', 'medium', 'high'],
      };
    }

    case 'ollama':
      // Ollama: OpenAI-compatible, all standard params
      return defaults;

    default:
      return defaults;
  }
}

// --- Parameter Tooltip ---

function ParamTooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex ml-1">
      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 rounded-md bg-popover px-3 py-2 text-[11px] text-popover-foreground shadow-md border opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-50 leading-relaxed">
        {text}
      </span>
    </span>
  );
}

// --- Edit Dialog ---

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
    providers: Record<
      string,
      {
        model_id: string;
        supports_vision?: boolean;
        supports_tools?: boolean;
        supports_structured_output?: boolean;
        is_image_model?: boolean;
      }[]
    >;
  };
  t: (key: string) => string;
}) {
  const [form, setForm] = useState<LLMTypeConfigUpdate>({});

  // Populate form when config changes (proper useEffect instead of render-time setState)
  useEffect(() => {
    if (config && open) {
      setForm({
        provider: config.effective.provider,
        model: config.effective.model,
        temperature: config.effective.temperature,
        top_p: config.effective.top_p,
        frequency_penalty: config.effective.frequency_penalty,
        presence_penalty: config.effective.presence_penalty,
        max_tokens: config.effective.max_tokens,
        timeout_seconds: config.effective.timeout_seconds,
        reasoning_effort: config.effective.reasoning_effort,
      });
    }
  }, [config, open]);

  const handleClose = () => {
    setForm({});
    onClose();
  };

  const handleSave = async () => {
    if (!config) return;
    // Build update: compare with defaults, send null for unchanged fields
    const update: LLMTypeConfigUpdate = {};
    const d = config.defaults;

    if (form.provider !== d.provider) update.provider = form.provider;
    if (form.model !== d.model) update.model = form.model;
    if (form.temperature !== d.temperature) update.temperature = form.temperature;
    if (form.top_p !== d.top_p) update.top_p = form.top_p;
    if (form.frequency_penalty !== d.frequency_penalty)
      update.frequency_penalty = form.frequency_penalty;
    if (form.presence_penalty !== d.presence_penalty)
      update.presence_penalty = form.presence_penalty;
    if (form.max_tokens !== d.max_tokens) update.max_tokens = form.max_tokens;
    if (form.timeout_seconds !== d.timeout_seconds) update.timeout_seconds = form.timeout_seconds;
    if (form.reasoning_effort !== d.reasoning_effort)
      update.reasoning_effort = form.reasoning_effort;

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

  // Filter models by required_capabilities from LLM type config
  const requiredCaps = config?.info.required_capabilities ?? [];
  const isOllamaWithDynamic = form.provider === 'ollama' && (ollamaData?.models?.length ?? 0) > 0;
  const modelSource = isOllamaWithDynamic
    ? ollamaData!.models
    : (metadata.providers[form.provider ?? ''] ?? []);
  const isImageType = config?.info.llm_type === 'image_generation';
  const availableModels = form.provider
    ? modelSource
        .filter(m => {
          // Image generation type: only show image models
          // Other types: only show non-image (chat) models
          if (isImageType && !m.is_image_model) return false;
          if (!isImageType && m.is_image_model) return false;
          if (requiredCaps.includes('vision') && !m.supports_vision) return false;
          if (requiredCaps.includes('tools') && !m.supports_tools) return false;
          if (requiredCaps.includes('structured_output') && !m.supports_structured_output)
            return false;
          return true;
        })
        .map(m => m.model_id)
    : [];

  const constraints = getModelConstraints(
    form.provider ?? '',
    form.model ?? '',
    form.reasoning_effort
  );

  const isModified = (field: keyof LLMTypeConfigUpdate) => {
    if (!config) return false;
    const defaultVal = config.defaults[field as keyof typeof config.defaults];
    return form[field] !== defaultVal;
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

        <div className="space-y-4 py-2 max-h-[60vh] overflow-y-auto pr-1">
          {/* Provider */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label>{t('settings.admin.llmConfig.fields.provider')}</Label>
              {isModified('provider') && (
                <Badge variant="default" className="text-[10px] px-1 py-0">
                  {t('settings.admin.llmConfig.types.overridden')}
                </Badge>
              )}
            </div>
            <Select
              value={form.provider ?? ''}
              onValueChange={v => setForm({ ...form, provider: v, model: '' })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.keys(metadata.providers).map(p => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Model */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label>{t('settings.admin.llmConfig.fields.model')}</Label>
              {isModified('model') && (
                <Badge variant="default" className="text-[10px] px-1 py-0">
                  {t('settings.admin.llmConfig.types.overridden')}
                </Badge>
              )}
            </div>
            {form.provider === 'ollama' && ollamaLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-1.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t('settings.admin.llmConfig.ollama.loading')}
              </div>
            ) : availableModels.length > 0 ? (
              <Select value={form.model ?? ''} onValueChange={v => setForm({ ...form, model: v })}>
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
                onChange={e => setForm({ ...form, model: e.target.value })}
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

          {/* Temperature */}
          {constraints.supportsTemperature && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Label>{t('settings.admin.llmConfig.fields.temperature')}</Label>
                <ParamTooltip text={t('settings.admin.llmConfig.tooltips.temperature')} />
                {isModified('temperature') && (
                  <Badge variant="default" className="text-[10px] px-1 py-0">
                    {t('settings.admin.llmConfig.types.overridden')}
                  </Badge>
                )}
              </div>
              {constraints.temperatureWarning && (
                <p className="text-[11px] text-amber-500">{t(constraints.temperatureWarning)}</p>
              )}
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max={constraints.temperatureMax}
                  step="0.1"
                  value={form.temperature ?? 0}
                  onChange={e => setForm({ ...form, temperature: parseFloat(e.target.value) })}
                  className="flex-1"
                />
                <span className="text-sm font-mono w-10 text-right">
                  {form.temperature?.toFixed(1)}
                </span>
              </div>
            </div>
          )}
          {!constraints.supportsTemperature && constraints.temperatureWarning && (
            <p className="text-[11px] text-amber-500 py-1">{t(constraints.temperatureWarning)}</p>
          )}

          {/* Max Tokens */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label>{t('settings.admin.llmConfig.fields.maxTokens')}</Label>
              <ParamTooltip text={t('settings.admin.llmConfig.tooltips.maxTokens')} />
              {isModified('max_tokens') && (
                <Badge variant="default" className="text-[10px] px-1 py-0">
                  {t('settings.admin.llmConfig.types.overridden')}
                </Badge>
              )}
            </div>
            <Input
              type="number"
              min="1"
              value={form.max_tokens ?? ''}
              onChange={e => setForm({ ...form, max_tokens: parseInt(e.target.value) || null })}
            />
          </div>

          {/* Top P — hidden for providers that don't support it */}
          {constraints.supportsTopP && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Label>{t('settings.admin.llmConfig.fields.topP')}</Label>
                <ParamTooltip text={t('settings.admin.llmConfig.tooltips.topP')} />
                {isModified('top_p') && (
                  <Badge variant="default" className="text-[10px] px-1 py-0">
                    {t('settings.admin.llmConfig.types.overridden')}
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={form.top_p ?? 1}
                  onChange={e => setForm({ ...form, top_p: parseFloat(e.target.value) })}
                  className="flex-1"
                />
                <span className="text-sm font-mono w-10 text-right">{form.top_p?.toFixed(2)}</span>
              </div>
            </div>
          )}

          {/* Frequency Penalty */}
          {constraints.supportsFrequencyPenalty && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Label>{t('settings.admin.llmConfig.fields.frequencyPenalty')}</Label>
                <ParamTooltip text={t('settings.admin.llmConfig.tooltips.frequencyPenalty')} />
                {isModified('frequency_penalty') && (
                  <Badge variant="default" className="text-[10px] px-1 py-0">
                    {t('settings.admin.llmConfig.types.overridden')}
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="-2"
                  max="2"
                  step="0.1"
                  value={form.frequency_penalty ?? 0}
                  onChange={e =>
                    setForm({ ...form, frequency_penalty: parseFloat(e.target.value) })
                  }
                  className="flex-1"
                />
                <span className="text-sm font-mono w-10 text-right">
                  {form.frequency_penalty?.toFixed(1)}
                </span>
              </div>
            </div>
          )}

          {/* Presence Penalty */}
          {constraints.supportsPresencePenalty && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Label>{t('settings.admin.llmConfig.fields.presencePenalty')}</Label>
                <ParamTooltip text={t('settings.admin.llmConfig.tooltips.presencePenalty')} />
                {isModified('presence_penalty') && (
                  <Badge variant="default" className="text-[10px] px-1 py-0">
                    {t('settings.admin.llmConfig.types.overridden')}
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="-2"
                  max="2"
                  step="0.1"
                  value={form.presence_penalty ?? 0}
                  onChange={e => setForm({ ...form, presence_penalty: parseFloat(e.target.value) })}
                  className="flex-1"
                />
                <span className="text-sm font-mono w-10 text-right">
                  {form.presence_penalty?.toFixed(1)}
                </span>
              </div>
            </div>
          )}

          {/* Timeout */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label>{t('settings.admin.llmConfig.fields.timeout')}</Label>
              <ParamTooltip text={t('settings.admin.llmConfig.tooltips.timeout')} />
              {isModified('timeout_seconds') && (
                <Badge variant="default" className="text-[10px] px-1 py-0">
                  {t('settings.admin.llmConfig.types.overridden')}
                </Badge>
              )}
            </div>
            <Input
              type="number"
              min="1"
              value={form.timeout_seconds ?? ''}
              onChange={e =>
                setForm({
                  ...form,
                  timeout_seconds: e.target.value ? parseInt(e.target.value) : null,
                })
              }
              placeholder={t('settings.admin.llmConfig.fields.timeoutPlaceholder')}
            />
          </div>

          {/* Reasoning Effort — only for providers/models that support it */}
          {constraints.supportsReasoningEffort && constraints.reasoningEffortOptions.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Label>{t('settings.admin.llmConfig.fields.reasoningEffort')}</Label>
                <ParamTooltip text={t('settings.admin.llmConfig.tooltips.reasoningEffort')} />
                {isModified('reasoning_effort') && (
                  <Badge variant="default" className="text-[10px] px-1 py-0">
                    {t('settings.admin.llmConfig.types.overridden')}
                  </Badge>
                )}
              </div>
              <Select
                value={form.reasoning_effort ?? '_disabled'}
                onValueChange={v =>
                  setForm({
                    ...form,
                    reasoning_effort: v === '_disabled' ? null : (v as ReasoningEffort),
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {/* Only show "None (disabled)" if the model actually supports effort="none" */}
                  {constraints.reasoningEffortOptions.includes('none') ? (
                    <SelectItem value="_disabled">
                      {t('settings.admin.llmConfig.fields.reasoningNone')}
                    </SelectItem>
                  ) : (
                    <SelectItem value="_disabled">
                      {t('settings.admin.llmConfig.fields.reasoningDefault')}
                    </SelectItem>
                  )}
                  {constraints.reasoningEffortOptions.map(opt => (
                    <SelectItem key={opt} value={opt}>
                      {opt.charAt(0).toUpperCase() + opt.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
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
                  {catConfigs.map(c => (
                    <LLMTypeCard key={c.llm_type} config={c} onEdit={setEditingConfig} t={t} />
                  ))}
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

'use client';

import { AlertCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import type {
  ReasoningBudgetRange,
  ReasoningEffortValue,
  ReasoningWidgetType,
} from '@/types/llm-config';
import { REASONING_DOC_TEXT } from './reasoningDocText';

/**
 * Single source of UI rendering for reasoning_effort.
 *
 * Replaces the regex-based getModelConstraints() that lived in
 * AdminLLMConfigSection.tsx. The shape of this widget is fully driven by
 * ModelCapabilities.reasoning_widget exposed by GET /llm-config/metadata.
 *
 * Philosophy A — raw truth: the dropdown / slider / toggle exposes
 * exactly what the API accepts. No silent UI→API mapping.
 */
interface ReasoningWidgetProps {
  widget: ReasoningWidgetType;
  enumValues?: string[] | null;
  budgetRange?: ReasoningBudgetRange | null;
  docI18nKey?: string | null;
  value: ReasoningEffortValue;
  onChange: (next: ReasoningEffortValue) => void;
  disabled?: boolean;
}

const PRESET_OFF = '__off__';
const PRESET_DYNAMIC = '__dynamic__';
const PRESET_CUSTOM = '__custom__';

export function ReasoningWidget({
  widget,
  enumValues,
  budgetRange,
  docI18nKey,
  value,
  onChange,
  disabled,
}: ReasoningWidgetProps) {
  if (widget === 'none') return null;

  const docText = docI18nKey ? REASONING_DOC_TEXT[docI18nKey] : undefined;

  if (widget === 'enum') {
    const allowed = enumValues ?? [];
    const current = value && 'effort' in value ? value.effort : '';
    const isInvalid = current !== '' && !allowed.includes(current);

    return (
      <div className="space-y-1">
        <Select
          value={current}
          onValueChange={v => onChange({ effort: v })}
          disabled={disabled || allowed.length === 0}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder="reasoning_effort" />
          </SelectTrigger>
          <SelectContent>
            {allowed.map(v => (
              <SelectItem key={v} value={v} className="text-xs">
                {v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {allowed.length === 1 && (
          <p className="text-[10px] text-muted-foreground italic">
            Forced to {allowed[0]} (only value accepted by this model).
          </p>
        )}
        {isInvalid && (
          <p role="alert" className="flex items-center gap-1 text-[10px] text-destructive">
            <AlertCircle className="h-3 w-3" />
            Invalid: {`'${current}'`} not in [{allowed.join(', ')}]
          </p>
        )}
        {docText && <p className="text-[10px] text-muted-foreground">{docText}</p>}
      </div>
    );
  }

  if (widget === 'budget_int') {
    const range = budgetRange;
    const currentBudget = value && 'budget' in value ? value.budget : null;
    const offSentinel = range?.off_sentinel ?? null;
    const dynamicSentinel = range?.dynamic_sentinel ?? null;

    let preset: string;
    if (currentBudget === null || currentBudget === undefined) preset = PRESET_CUSTOM;
    else if (offSentinel !== null && currentBudget === offSentinel) preset = PRESET_OFF;
    else if (dynamicSentinel !== null && currentBudget === dynamicSentinel) preset = PRESET_DYNAMIC;
    else preset = PRESET_CUSTOM;

    const handlePreset = (next: string) => {
      if (next === PRESET_OFF && offSentinel !== null) onChange({ budget: offSentinel });
      else if (next === PRESET_DYNAMIC && dynamicSentinel !== null)
        onChange({ budget: dynamicSentinel });
      else if (next === PRESET_CUSTOM) {
        // Default to range.min for the custom slot.
        onChange({ budget: range?.min ?? 0 });
      }
    };

    return (
      <div className="space-y-1">
        <Select value={preset} onValueChange={handlePreset} disabled={disabled}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {offSentinel !== null && (
              <SelectItem value={PRESET_OFF} className="text-xs">
                Off ({offSentinel})
              </SelectItem>
            )}
            {dynamicSentinel !== null && (
              <SelectItem value={PRESET_DYNAMIC} className="text-xs">
                Dynamic ({dynamicSentinel})
              </SelectItem>
            )}
            <SelectItem value={PRESET_CUSTOM} className="text-xs">
              Custom budget…
            </SelectItem>
          </SelectContent>
        </Select>
        {preset === PRESET_CUSTOM && range && (
          <Input
            type="number"
            min={range.min}
            max={range.max}
            value={typeof currentBudget === 'number' ? currentBudget : range.min}
            onChange={e => {
              const n = Number(e.target.value);
              if (!Number.isNaN(n)) onChange({ budget: n });
            }}
            disabled={disabled}
            className="h-8 text-xs"
            aria-label="Reasoning budget (tokens)"
          />
        )}
        {range && (
          <p className="text-[10px] text-muted-foreground">
            Range: {range.min}–{range.max} tokens.
          </p>
        )}
        {docText && <p className="text-[10px] text-muted-foreground">{docText}</p>}
      </div>
    );
  }

  // widget === 'toggle_budget'
  const enabled = value && 'enabled' in value ? value.enabled : false;
  const currentBudget =
    value && 'enabled' in value && value.budget !== undefined && value.budget !== null
      ? value.budget
      : null;

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Switch
          checked={enabled}
          onCheckedChange={(next: boolean) => {
            if (next) onChange({ enabled: true });
            else onChange({ enabled: false });
          }}
          disabled={disabled}
          aria-label="Enable thinking"
        />
        <span className="text-xs text-muted-foreground">
          {enabled ? 'Thinking enabled' : 'Thinking disabled'}
        </span>
      </div>
      {enabled && budgetRange && (
        <Input
          type="number"
          min={budgetRange.min}
          max={budgetRange.max}
          value={currentBudget ?? ''}
          placeholder={`Budget (${budgetRange.min}–${budgetRange.max}, blank = max)`}
          onChange={e => {
            const raw = e.target.value;
            if (raw === '') onChange({ enabled: true });
            else {
              const n = Number(raw);
              if (!Number.isNaN(n)) onChange({ enabled: true, budget: n });
            }
          }}
          disabled={disabled}
          className="h-8 text-xs"
          aria-label="Reasoning budget (tokens)"
        />
      )}
      {docText && <p className="text-[10px] text-muted-foreground">{docText}</p>}
    </div>
  );
}

'use client';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useFieldA11y } from '@/components/ui/field';
import type {
  ModelCapabilities,
  ReasoningBudgetRange,
  ReasoningEffortValue,
  ReasoningIntentValue,
  ReasoningLevel,
} from '@/types/llm-config';
import { REASONING_DOC_TEXT } from './reasoningDocText';
import { EMPTY_INTENT, withBudget, withExclude, withLevel } from './reasoningHelpers';

/**
 * The single reasoning control, for every provider (ADR-245).
 *
 * It replaced three sub-components dispatched on `llm_models.reasoning_widget`:
 * an enum dropdown, a budget preset + custom int, and an enabled/budget
 * toggle. The shape of the stored value no longer varies, so neither does the
 * control — what varies is what a given model OFFERS, which the backend
 * publishes as a resolved profile: the ladder, whether reasoning can be turned
 * off, whether a token budget is expressible, and whether excluding the
 * reasoning from the output reaches that provider at all.
 *
 * Philosophy A — raw truth: every option shown here is one the API accepts for
 * this exact model, because the payload driving it comes from the same
 * function the API validates with.
 *
 * Identity comes from `useFieldA11y` (`useId`), never from a literal id: this
 * widget is rendered inside a dialog that can be mounted more than once, and
 * two live `id="reasoning-budget"` attributes would send every label to the
 * first one. The compact `space-y` here is deliberate and does NOT contradict
 * the app-wide 12px label→control gap: the whole widget is ONE field of the
 * configuration form, already labelled by its section, and these are its
 * sub-controls — the same reason ADR-207 exempts the in-row micro-editor.
 */
interface ReasoningWidgetProps {
  caps: ModelCapabilities | undefined;
  value: ReasoningEffortValue;
  onChange: (next: ReasoningEffortValue) => void;
  disabled?: boolean;
  /** Accepts i18next interpolation options — the range hint needs them. */
  t: (key: string, options?: Record<string, unknown>) => string;
}

/** Sentinel for "no override" in the level Select — Radix forbids an empty
 * string as an item value, and `provider_default` is a real level the API
 * accepts, so the two must stay distinguishable. */
const NO_OVERRIDE = '__none__';

/** Shared by every sub-control: they all edit the same intent. */
interface FieldProps {
  value: ReasoningEffortValue;
  onChange: (next: ReasoningEffortValue) => void;
  disabled?: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}

/** Depth: the ladder the model published, plus "no override". */
function LevelField({
  levels,
  value,
  onChange,
  disabled,
  t,
}: FieldProps & { levels: ReasoningLevel[] }) {
  const handle = (next: string) =>
    onChange(
      next === NO_OVERRIDE ? null : withLevel(value ?? EMPTY_INTENT, next as ReasoningLevel)
    );

  return (
    <>
      <Select value={value ? value.level : NO_OVERRIDE} onValueChange={handle} disabled={disabled}>
        <SelectTrigger
          className="h-8 text-xs"
          aria-label={t('settings.admin.llmConfig.fields.reasoningEffort')}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NO_OVERRIDE} className="text-xs">
            {t('settings.admin.llmConfig.fields.reasoningDefault')}
          </SelectItem>
          {levels.map(level => (
            <SelectItem key={level} value={level} className="text-xs">
              {t(`settings.admin.llmConfig.reasoningLevels.${level}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {levels.length === 1 && (
        <p className="text-[10px] text-muted-foreground italic">
          {t('settings.admin.llmConfig.constraints.reasoningSingleLevel')}
        </p>
      )}
    </>
  );
}

/** An explicit token budget, for the families that can express one. */
function BudgetField({
  range,
  value,
  onChange,
  disabled,
  t,
}: FieldProps & { range: ReasoningBudgetRange }) {
  const budget = value?.budget_tokens ?? null;
  const outOfRange = budget !== null && (budget < range.min || budget > range.max);
  const hint = t('settings.admin.llmConfig.constraints.reasoningBudgetRange', {
    min: range.min,
    max: range.max,
  });
  // The hint doubles as the error text: it already states the only rule this
  // field has, and the backend rejects the same bound with the same numbers.
  const { fieldId, errorId, controlProps } = useFieldA11y({ error: outOfRange ? hint : undefined });

  const handle = (raw: string) => {
    const base: ReasoningIntentValue = value ?? EMPTY_INTENT;
    if (raw === '') {
      onChange(withBudget(base, null));
      return;
    }
    const parsed = Number(raw);
    if (!Number.isNaN(parsed)) onChange(withBudget(base, parsed));
  };

  return (
    <div className="space-y-1">
      <Label htmlFor={fieldId} className="text-[11px] text-muted-foreground">
        {t('settings.admin.llmConfig.fields.reasoningBudget')}
      </Label>
      <Input
        {...controlProps}
        type="number"
        inputMode="numeric"
        min={range.min}
        max={range.max}
        step={1}
        value={budget ?? ''}
        placeholder={`${range.min}–${range.max}`}
        onChange={e => handle(e.target.value)}
        disabled={disabled}
        className="h-8 text-xs"
      />
      <p
        id={errorId}
        className={
          outOfRange ? 'text-[10px] text-destructive' : 'text-[10px] text-muted-foreground'
        }
      >
        {hint}
      </p>
    </div>
  );
}

/** Orthogonal to depth, and only where the renderer actually sends it. */
function ExcludeField({ value, onChange, disabled, t }: FieldProps) {
  const { fieldId } = useFieldA11y({});

  return (
    <div className="flex items-start gap-2">
      <Switch
        id={fieldId}
        checked={value?.exclude_from_output ?? false}
        onCheckedChange={(next: boolean) => onChange(withExclude(value ?? EMPTY_INTENT, next))}
        disabled={disabled}
        className="mt-0.5 shrink-0"
      />
      <Label htmlFor={fieldId} className="text-xs text-muted-foreground font-normal">
        {t('settings.admin.llmConfig.fields.reasoningExclude')}
      </Label>
    </div>
  );
}

export function ReasoningWidget({ caps, value, onChange, disabled, t }: ReasoningWidgetProps) {
  const levels: ReasoningLevel[] = caps?.reasoning_levels ?? [];
  if (levels.length === 0) return null;

  const docKey = caps?.reasoning_doc_i18n_key;
  const docText = docKey ? REASONING_DOC_TEXT[docKey] : undefined;
  const range = caps?.reasoning_budget_range ?? null;
  const shared: FieldProps = { value, onChange, disabled, t };

  return (
    <div className="space-y-2">
      <LevelField {...shared} levels={levels} />
      {caps?.reasoning_supports_budget && range && <BudgetField {...shared} range={range} />}
      {caps?.reasoning_supports_exclude && <ExcludeField {...shared} />}
      {docText && <p className="text-[10px] text-muted-foreground">{docText}</p>}
    </div>
  );
}

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
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  MEMORY_CATEGORIES,
  getEmotionalEmoji,
  type MemoryCategory,
  type MemoryLimits,
} from '@/hooks/useMemories';
import {
  countCharacters,
  excessCharacters,
  isTooShort,
  memoryTextBounds,
  type MemoryTextField,
  type TextBound,
} from '@/lib/memories/text-bounds';
import { cn } from '@/lib/utils';

export const CATEGORY_ICONS: Record<MemoryCategory, string> = {
  preference: '💡',
  personal: '📋',
  relationship: '👥',
  event: '📅',
  pattern: '🔄',
  sensitivity: '⚠️',
  procedural: '📌',
};

/** What the create and edit dialogs both fill in. */
export interface MemoryFormData {
  content: string;
  category: MemoryCategory;
  usage_nuance: string;
  emotional_weight: number;
  importance: number;
  trigger_topic: string;
}

export const EMPTY_MEMORY_FORM: MemoryFormData = {
  content: '',
  category: 'personal',
  usage_nuance: '',
  emotional_weight: 0,
  importance: 0.7,
  trigger_topic: '',
};

interface FieldFooterProps {
  lng: Language;
  id: string | undefined;
  text: string;
  bound: TextBound | undefined;
  help?: string;
}

/** The line under a text field: what it is for, and how much of its bound is used. */
function FieldFooter({ lng, id, text, bound, help }: FieldFooterProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex items-start justify-between gap-3">
      {help && <p className="text-xs text-muted-foreground">{help}</p>}
      {bound && (
        <p
          id={id}
          className={cn(
            'ml-auto shrink-0 text-xs',
            excessCharacters(text, bound) > 0 ? 'text-destructive' : 'text-foreground/80'
          )}
        >
          {t('memories.characters', { count: countCharacters(text), max: bound.max })}
        </p>
      )}
    </div>
  );
}

interface MemoryFormFieldsProps {
  lng: Language;
  /** Keeps the two dialogs' field ids apart. */
  idPrefix: 'create' | 'edit';
  form: MemoryFormData;
  onChange: (form: MemoryFormData) => void;
  /** The bounds the API published; unknown until the list has answered. */
  limits: MemoryLimits | undefined;
  contentLabel: string;
  categoryLabel: (category: MemoryCategory) => string;
  autoFocusContent?: boolean;
}

/**
 * The fields of a memory, with the bounds the API would refuse them by.
 *
 * A text past its bound stays in its field, marked and counted: `maxLength` would cut
 * a paste without a word, and it counts UTF-16 units where the API counts characters.
 * What keeps it from leaving is `isMemoryTextSavable`, read by the dialog's button.
 */
export function MemoryFormFields({
  lng,
  idPrefix,
  form,
  onChange,
  limits,
  contentLabel,
  categoryLabel,
  autoFocusContent = false,
}: MemoryFormFieldsProps) {
  const { t } = useTranslation(lng);
  const bounds = limits ? memoryTextBounds(limits) : undefined;
  const update = (changes: Partial<MemoryFormData>) => onChange({ ...form, ...changes });
  // Only a bound prints a count, and a description must never point at nothing.
  const countId = (field: MemoryTextField) => (bounds ? `${idPrefix}-${field}-count` : undefined);

  const refusal = (field: MemoryTextField): string | undefined => {
    if (!bounds) return undefined;
    const bound = bounds[field];
    // One sentence for the whole overflow: an alert is announced again whenever its text
    // changes, and the count beside the field is the part that moves.
    if (excessCharacters(form[field], bound) > 0) {
      return t('memories.text_too_long', { max: bound.max });
    }
    return isTooShort(form[field], bound)
      ? t('memories.text_too_short', { min: bound.min })
      : undefined;
  };

  return (
    <div className="grid gap-4 py-4">
      {/* Content */}
      <div className="grid gap-3">
        <Textarea
          id={`${idPrefix}-content`}
          label={contentLabel}
          value={form.content}
          onChange={e => update({ content: e.target.value })}
          placeholder={t('memories.content_placeholder')}
          rows={3}
          autoFocus={autoFocusContent}
          error={refusal('content')}
          aria-describedby={countId('content')}
        />
        <FieldFooter
          lng={lng}
          id={countId('content')}
          text={form.content}
          bound={bounds?.content}
        />
      </div>
      {/* Category */}
      <div className="grid gap-3">
        <Label htmlFor={`${idPrefix}-category`}>{t('memories.field_category')}</Label>
        <Select
          value={form.category}
          onValueChange={value => update({ category: value as MemoryCategory })}
        >
          <SelectTrigger id={`${idPrefix}-category`}>
            <SelectValue placeholder={t('memories.select_category')} />
          </SelectTrigger>
          <SelectContent>
            {MEMORY_CATEGORIES.map(category => (
              <SelectItem key={category} value={category}>
                {CATEGORY_ICONS[category]} {categoryLabel(category)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {/* Usage Nuance */}
      <div className="grid gap-3">
        <Input
          id={`${idPrefix}-nuance`}
          label={t('memories.field_usage_nuance')}
          value={form.usage_nuance}
          onChange={e => update({ usage_nuance: e.target.value })}
          placeholder={t('memories.nuance_placeholder')}
          error={refusal('usage_nuance')}
          aria-describedby={countId('usage_nuance')}
        />
        <FieldFooter
          lng={lng}
          id={countId('usage_nuance')}
          text={form.usage_nuance}
          bound={bounds?.usage_nuance}
          help={t('memories.nuance_help')}
        />
      </div>
      {/* Trigger Topic */}
      <div className="grid gap-3">
        <Input
          id={`${idPrefix}-trigger`}
          label={t('memories.field_trigger_topic')}
          value={form.trigger_topic}
          onChange={e => update({ trigger_topic: e.target.value })}
          placeholder={t('memories.trigger_placeholder')}
          error={refusal('trigger_topic')}
          aria-describedby={countId('trigger_topic')}
        />
        <FieldFooter
          lng={lng}
          id={countId('trigger_topic')}
          text={form.trigger_topic}
          bound={bounds?.trigger_topic}
          help={t('memories.trigger_help')}
        />
      </div>
      {/* Emotional Weight */}
      <div className="grid gap-2">
        <div className="flex items-center justify-between">
          <Label htmlFor={`${idPrefix}-emotional`}>{t('memories.field_emotional_weight')}</Label>
          <span className="text-sm flex items-center gap-1">
            {getEmotionalEmoji(form.emotional_weight)} {form.emotional_weight}
          </span>
        </div>
        <Slider
          id={`${idPrefix}-emotional`}
          aria-label={t('memories.field_emotional_weight')}
          min={-10}
          max={10}
          step={1}
          value={[form.emotional_weight]}
          onValueChange={(value: number[]) => update({ emotional_weight: value[0] })}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>-10 ({t('memories.emotional_negative')})</span>
          <span>+10 ({t('memories.emotional_positive')})</span>
        </div>
      </div>
      {/* Importance */}
      <div className="grid gap-2">
        <div className="flex items-center justify-between">
          <Label htmlFor={`${idPrefix}-importance`}>{t('memories.field_importance')}</Label>
          <span className="text-sm">★ {(form.importance * 100).toFixed(0)}%</span>
        </div>
        <Slider
          id={`${idPrefix}-importance`}
          aria-label={t('memories.field_importance')}
          min={0}
          max={1}
          step={0.1}
          value={[form.importance]}
          onValueChange={(value: number[]) => update({ importance: value[0] })}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>0% ({t('memories.importance_low')})</span>
          <span>100% ({t('memories.importance_high')})</span>
        </div>
      </div>
    </div>
  );
}

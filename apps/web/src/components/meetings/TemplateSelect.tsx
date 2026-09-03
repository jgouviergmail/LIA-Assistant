'use client';

/**
 * The one template picker (ADR-259): grouped by category in library order,
 * an optional « automatic » entry first, the chosen name on the trigger.
 *
 * Shared by the settings (default format, automatic allowed) and the format
 * dialog on a meeting (a concrete template is required there). The API stores
 * `null` for automatic; this component speaks refs and null, never the
 * sentinel.
 */

import { useMemo } from 'react';

import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { TemplateCategoryGlyph } from '@/components/meetings/templateCategoryIcons';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { groupByCategory } from '@/lib/meetings/templates';
import type { MeetingTemplateSummary } from '@/types/meetings';

/** The select value standing for « no template: LIA chooses » (never sent to the API). */
export const AUTO_TEMPLATE = 'auto';

export interface TemplateSelectProps {
  lng: Language;
  id: string;
  /** Already translated; names the trigger. */
  label: string;
  templates: MeetingTemplateSummary[];
  /** A template ref, or null for automatic (only meaningful with `autoLabel`). */
  value: string | null;
  onChange: (ref: string | null) => void;
  /** When given, an « automatic » entry is offered first and null is a valid value. */
  autoLabel?: string;
  /** Already translated caption under the control. */
  hint?: string;
  /** Already translated; shown on the trigger while nothing is chosen and no automatic entry exists. */
  placeholder?: string;
  triggerClassName?: string;
  /** `inline` lays the label and the control on one row (banners, toolbars). */
  layout?: 'stack' | 'inline';
}

export function TemplateSelect({
  lng,
  id,
  label,
  templates,
  value,
  onChange,
  autoLabel,
  hint,
  placeholder,
  triggerClassName,
  layout = 'stack',
}: TemplateSelectProps) {
  const { t } = useTranslation(lng);
  const groups = useMemo(() => groupByCategory(templates), [templates]);
  const selectValue = value ?? (autoLabel ? AUTO_TEMPLATE : '');
  return (
    <div className={layout === 'inline' ? 'flex flex-wrap items-center gap-3' : 'space-y-3'}>
      <Label htmlFor={id} className={layout === 'inline' ? 'shrink-0' : undefined}>
        {label}
      </Label>
      <Select
        value={selectValue}
        onValueChange={next => onChange(next === AUTO_TEMPLATE ? null : next)}
      >
        <SelectTrigger id={id} className={triggerClassName}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {autoLabel && <SelectItem value={AUTO_TEMPLATE}>{autoLabel}</SelectItem>}
          {[...groups.entries()].map(([category, items], index) => (
            <SelectGroup key={category}>
              {/* A heading reads as a heading: separated from the group above,
                  its glyph in the theme colour, the items indented under it. */}
              {(index > 0 || autoLabel) && <SelectSeparator />}
              <SelectLabel className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-primary">
                <TemplateCategoryGlyph category={category} className="h-3.5 w-3.5 shrink-0" />
                {t(`meetings.templates.category.${category}`)}
              </SelectLabel>
              {items.map(item => (
                <SelectItem key={item.ref} value={item.ref} className="pl-9">
                  {item.name}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

'use client';

/**
 * What a gallery is narrowed to (ADR-279).
 *
 * The same shape as the workboard's filter block (ADR-276), deliberately: a
 * grid rather than a wrapping row of fixed widths — one column on a phone, two
 * from `sm`, four from `xl`, so the fields share the width and their labels sit
 * on the same baselines — a titled header carrying the icon and « clear », and
 * a FOLD below `lg`.
 *
 * Three rules the controls obey:
 *
 * - an unset filter costs NO query parameter (`undefined`, never `''`), so the
 *   server keeps its own default;
 * - « expiring soon » is a real question a person asks about files that vanish,
 *   so it is one click, not a date to type;
 * - the folded summary says what the block HOLDS — the exact count and the
 *   words of the controls — because a fold whose summary says nothing is a fold
 *   the reader opens to find out.
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock, CalendarDays, Filter, Search, SortAsc, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { activeAssetFilterCount, describeAssetFilters } from '@/lib/generated-assets/filters';
import type { GeneratedAssetFilters, GeneratedAssetSort } from '@/types/generated-assets';

/** Search needle cap — the API's own bound, published to the field (ADR-184). */
export const ASSET_SEARCH_MAX_CHARS = 200;

const SORTS: readonly GeneratedAssetSort[] = [
  'created_desc',
  'created_asc',
  'expires_asc',
  'name_asc',
];

/** Windows a reader actually asks for, in days back from now. */
const CREATED_WINDOWS: readonly number[] = [1, 7, 30];

/** « About to go » — hours ahead of now. */
const EXPIRY_WINDOWS: readonly number[] = [1, 6];

const GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';

export interface GeneratedAssetFiltersBarProps {
  filters: GeneratedAssetFilters;
  onChange: (filters: GeneratedAssetFilters) => void;
  /**
   * Fold the block behind a summary.
   *
   * Set below `lg`, where the reader came to look at their files and four
   * fields plus a button push the first card off the screen.
   */
  collapsible?: boolean;
}

/**
 * An instant N days before now, as the API reads it.
 *
 * @param days - How far back.
 * @returns An ISO-8601 instant.
 */
function daysAgo(days: number): string {
  return new Date(Date.now() - days * 24 * 3600 * 1000).toISOString();
}

/**
 * An instant N hours after now.
 *
 * @param hours - How far ahead.
 * @returns An ISO-8601 instant.
 */
function hoursAhead(hours: number): string {
  return new Date(Date.now() + hours * 3600 * 1000).toISOString();
}

export function GeneratedAssetFiltersBar({
  filters,
  onChange,
  collapsible = false,
}: GeneratedAssetFiltersBarProps) {
  const { t } = useTranslation();
  const set = (patch: Partial<GeneratedAssetFilters>) => onChange({ ...filters, ...patch });

  const clearButton = (
    <Button variant="outline" size="sm" onClick={() => onChange({})}>
      <X className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
      {t('settings.generated_assets.filters.reset')}
    </Button>
  );

  const controls = (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="space-y-2">
        <Label htmlFor="ga-q" className="flex items-center gap-2 text-sm">
          <Search className={GLYPH} aria-hidden="true" />
          {t('settings.generated_assets.filters.search')}
        </Label>
        <Input
          id="ga-q"
          value={filters.q ?? ''}
          maxLength={ASSET_SEARCH_MAX_CHARS}
          placeholder={t('settings.generated_assets.filters.search')}
          onChange={event => set({ q: event.target.value || undefined })}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="ga-created" className="flex items-center gap-2 text-sm">
          <CalendarDays className={GLYPH} aria-hidden="true" />
          {t('settings.generated_assets.filters.created')}
        </Label>
        <Select
          value={filters.createdAfter ? String(filters.createdAfter) : 'any'}
          onValueChange={value => set({ createdAfter: value === 'any' ? undefined : value })}
        >
          <SelectTrigger id="ga-created" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">
              {t('settings.generated_assets.filters.any_date')}
            </SelectItem>
            {CREATED_WINDOWS.map(days => (
              <SelectItem key={days} value={daysAgo(days)}>
                {t('settings.generated_assets.filters.last_days', { count: days })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="ga-expiring" className="flex items-center gap-2 text-sm">
          <CalendarClock className={GLYPH} aria-hidden="true" />
          {t('settings.generated_assets.filters.expiring')}
        </Label>
        <Select
          value={filters.expiresBefore ? String(filters.expiresBefore) : 'any'}
          onValueChange={value => set({ expiresBefore: value === 'any' ? undefined : value })}
        >
          <SelectTrigger id="ga-expiring" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">
              {t('settings.generated_assets.filters.any_expiry')}
            </SelectItem>
            {EXPIRY_WINDOWS.map(hours => (
              <SelectItem key={hours} value={hoursAhead(hours)}>
                {t('settings.generated_assets.filters.within_hours', { count: hours })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="ga-sort" className="flex items-center gap-2 text-sm">
          <SortAsc className={GLYPH} aria-hidden="true" />
          {t('settings.generated_assets.filters.sort')}
        </Label>
        <Select
          value={filters.sort ?? 'created_desc'}
          onValueChange={value => set({ sort: value as GeneratedAssetSort })}
        >
          <SelectTrigger id="ga-sort" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORTS.map(sort => (
              <SelectItem key={sort} value={sort}>
                {t(`settings.generated_assets.filters.sort_${sort}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );

  if (collapsible) {
    return (
      <FoldedFilters filters={filters}>
        {controls}
        {clearButton}
      </FoldedFilters>
    );
  }

  return (
    <section
      aria-label={t('settings.generated_assets.filters.title')}
      className="rounded-xl border border-border/50 bg-muted/20 p-3"
    >
      {/* A title always carries an icon, in the theme colour. « Clear » belongs
          on the title's own line: at the end of a wrapping row of controls it
          lands wherever the last field happens to stop. */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Filter className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('settings.generated_assets.filters.title')}
        </h3>
        {clearButton}
      </div>
      {controls}
    </section>
  );
}

/**
 * The phone shape: a summary that says what is narrowed, and the controls under it.
 *
 * The badge is the EXACT number of active narrowings and the description their
 * own words, both from `lib/generated-assets/filters.ts` — which the empty
 * state reads too, so the gallery cannot say « no match » while the summary
 * says nothing is filtered.
 */
function FoldedFilters({
  filters,
  children,
}: {
  filters: GeneratedAssetFilters;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const count = activeAssetFilterCount(filters);
  const described = describeAssetFilters(filters, t);
  return (
    <Disclosure
      icon={Filter}
      title={t('settings.generated_assets.filters.title')}
      badge={count > 0 ? count : undefined}
      badgeClassName={count > 0 ? 'bg-primary/15 text-primary' : undefined}
      description={described || t('settings.generated_assets.filters.none')}
    >
      <div className="space-y-3">{children}</div>
    </Disclosure>
  );
}

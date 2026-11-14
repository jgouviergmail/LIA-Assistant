'use client';

import { useId, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { DISPLAY_SEARCH_MAX_LENGTH } from '@/lib/constants';
import { Filter } from '@/lib/icons';
import { Disclosure, type DisclosureProps } from './disclosure';
import { Label } from './label';
import { SearchInput } from './search-input';

/**
 * Where the controls stop sharing a row: the exact complement of Tailwind's
 * `sm:`, the width from which `ListControls` lays them side by side. Asked as
 * « is this a phone », so the server and a first paint answer « no ».
 */
export const LIST_FILTERS_FOLD = 'not all and (min-width: 40rem)';

/** Between two narrowings on the folded line, as the workboard's fold joins its own. */
const JOIN = ' · ';

interface Choice<T extends string> {
  value: T;
  label: string;
}

/** One search presentation; each source keeps its own debounce and query contract. */
export function ListSearch({
  query,
  onQuery,
  searchLabel,
  debounceMs = 0,
  loading = false,
  maxLength = DISPLAY_SEARCH_MAX_LENGTH,
}: {
  query: string;
  onQuery: (query: string) => void;
  searchLabel: string;
  debounceMs?: number;
  loading?: boolean;
  maxLength?: number;
}) {
  return (
    <div className="w-full max-w-xl">
      <SearchInput
        value={query}
        onSearchChange={onQuery}
        debounceMs={debounceMs}
        loading={loading}
        maxLength={maxLength}
        placeholder={searchLabel}
        aria-label={searchLabel}
        className="h-11 rounded-full"
      />
    </div>
  );
}

/** Labels precede equally sized controls and share a fixed column on mobile. */
export function ListField({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="flex w-full min-w-0 items-center gap-2 sm:w-auto">
      <Label htmlFor={htmlFor} className="w-24 shrink-0 text-sm text-muted-foreground sm:w-auto">
        {label}
      </Label>
      <div className="min-w-0 flex-1 sm:w-48 sm:flex-none">{children}</div>
    </div>
  );
}

/** Controls use full rows on phones; quick chips remain a separate wrapping row. */
export function ListControls({ children, chips }: { children?: ReactNode; chips?: ReactNode }) {
  return (
    <div className="space-y-3">
      {children && (
        <div className="grid grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center">
          {children}
        </div>
      )}
      {chips && <div className="flex flex-wrap items-center gap-2">{chips}</div>}
    </div>
  );
}

/** Native choice semantics, shared by the list's ordering and optional filters. */
export function ListChoice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly Choice<T>[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <ListField label={label} htmlFor={id}>
      <select
        id={id}
        value={value}
        onChange={event => {
          const choice = options.find(option => option.value === event.target.value);
          if (choice) onChange(choice.value);
        }}
        className="h-11 w-full min-w-0 rounded-lg border border-input bg-[color:var(--lia-field-background,var(--color-background))] px-3 text-base text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-ring md:text-sm"
      >
        {options.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </ListField>
  );
}

/**
 * On a phone the controls wait behind « Filters » (owner, 2026-11-11).
 *
 * One control per row above one column of cards is a wall, and the reader came
 * for the list. Folded, the block is an index entry: it says HOW MANY
 * narrowings apply and names them in the words their own controls carry, so
 * nobody opens it to find out whether something is filtered. `active` is
 * declared by the caller, which alone knows what is a narrowing and what is a
 * default; an ordering is not one.
 *
 * Closed means unmounted (`Disclosure`), which costs nothing here: every
 * control is controlled by the list above it. From `sm` up nothing changes.
 */
export function ListFilters({
  active,
  surface,
  children,
}: {
  /** The narrowings in force, already translated, in control order. */
  active: readonly string[];
  /** `nested` when the toolbar already sits on a card. */
  surface?: DisclosureProps['surface'];
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const folded = useMediaQuery(LIST_FILTERS_FOLD);
  if (!folded) return <>{children}</>;
  return (
    <Disclosure
      icon={Filter}
      title={t('common.filters')}
      badge={active.length > 0 ? active.length : undefined}
      badgeClassName={active.length > 0 ? 'bg-primary/15 text-primary' : undefined}
      description={active.length > 0 ? active.join(JOIN) : t('common.filters_none')}
      surface={surface}
    >
      {children}
    </Disclosure>
  );
}

/** Search above wrapping controls, following the dashboard/relations layout. */
export function ListToolbar<T extends string>({
  query,
  onQuery,
  searchLabel,
  sort,
  onSort,
  sortLabel,
  sortOptions,
  active,
  surface,
  children,
  chips,
}: {
  query: string;
  onQuery: (query: string) => void;
  searchLabel: string;
  sort: T;
  onSort: (sort: T) => void;
  sortLabel: string;
  sortOptions: readonly Choice<T>[];
  /** What narrows the list beyond the search words — see `ListFilters`. */
  active: readonly string[];
  surface?: DisclosureProps['surface'];
  children?: ReactNode;
  chips?: ReactNode;
}) {
  return (
    <div className="space-y-3">
      <ListSearch query={query} onQuery={onQuery} searchLabel={searchLabel} />
      <ListFilters active={active} surface={surface}>
        <ListControls chips={chips}>
          {children}
          <ListChoice label={sortLabel} value={sort} options={sortOptions} onChange={onSort} />
        </ListControls>
      </ListFilters>
    </div>
  );
}

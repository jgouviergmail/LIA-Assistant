'use client';

import { useId, type ReactNode } from 'react';
import { DISPLAY_SEARCH_MAX_LENGTH } from '@/lib/constants';
import { Label } from './label';
import { SearchInput } from './search-input';

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
        className="h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-ring md:text-sm"
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

/** Search above wrapping controls, following the dashboard/relations layout. */
export function ListToolbar<T extends string>({
  query,
  onQuery,
  searchLabel,
  sort,
  onSort,
  sortLabel,
  sortOptions,
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
  children?: ReactNode;
  chips?: ReactNode;
}) {
  return (
    <div className="space-y-3">
      <ListSearch query={query} onQuery={onQuery} searchLabel={searchLabel} />
      <ListControls chips={chips}>
        {children}
        <ListChoice label={sortLabel} value={sort} options={sortOptions} onChange={onSort} />
      </ListControls>
    </div>
  );
}

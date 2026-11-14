'use client';

/**
 * SelectionBar — the bar above a list while rows are selected (ADR-259).
 *
 * Exact count, a « select every row of this page » checkbox that states the
 * partial state natively (`indeterminate`), a clear, and the actions the
 * caller composes as children — bulk destruction SOLID red at the toolbar
 * geometry (ADR-207). Strings come translated from the caller (ADR-206). The
 * row checkboxes live in the list; this bar only reads the selection.
 *
 * `compact` is the one line a narrow column can hold (ADR-369 amendment
 * 2026-11-11): the clear becomes an icon beside the count, named by the same
 * label, and the count and the actions never shrink, so a caller that hands
 * `barRef` can measure whether its actions still fit.
 */

import { useEffect, useRef, type ReactNode, type Ref } from 'react';
import { X } from '@/lib/icons';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import type { PageSelectionState } from '@/lib/selection';

export interface SelectionBarProps {
  /** Names the region for assistive technology (already translated). */
  regionLabel: string;
  /** The count sentence (already translated). */
  countLabel: string;
  /** Accessible name of the select-all checkbox (already translated). */
  selectAllLabel: string;
  /** Label of the clear button (already translated). */
  clearLabel: string;
  pageState: PageSelectionState;
  onSelectAll: () => void;
  onClear: () => void;
  /** The actions, rendered after the clear button. */
  children: ReactNode;
  className?: string;
  /** Keep the page checkbox mounted while a caller hides unavailable bulk actions. */
  showActions?: boolean;
  selectAllDisabled?: boolean;
  /** One line: the clear is an icon beside the count, nothing shrinks. */
  compact?: boolean;
  /** The bar's element, for a caller that measures its room. */
  barRef?: Ref<HTMLDivElement>;
}

export function SelectionBar({
  regionLabel,
  countLabel,
  selectAllLabel,
  clearLabel,
  pageState,
  onSelectAll,
  onClear,
  children,
  className,
  showActions = true,
  selectAllDisabled = false,
  compact = false,
  barRef,
}: SelectionBarProps) {
  const allRef = useRef<HTMLInputElement>(null);

  // `indeterminate` is a DOM property, not an attribute: it is synchronized
  // with the external system (the checkbox element) after each render.
  useEffect(() => {
    if (allRef.current) allRef.current.indeterminate = pageState === 'some';
  }, [pageState]);

  const clear = () => {
    allRef.current?.focus();
    onClear();
  };

  return (
    <div
      ref={barRef}
      role="region"
      aria-label={regionLabel}
      className={cn(
        'flex flex-wrap items-center rounded-lg border border-primary/30 bg-primary/5',
        compact ? 'gap-1 px-2 py-1' : 'gap-3 px-3 py-2',
        className
      )}
    >
      <label
        className={cn(
          'flex items-center gap-2 text-sm',
          compact ? 'h-9 shrink-0 whitespace-nowrap' : 'h-11'
        )}
      >
        <Checkbox
          ref={allRef}
          checked={pageState === 'all'}
          onChange={() => !selectAllDisabled && (pageState === 'all' ? onClear() : onSelectAll())}
          aria-disabled={selectAllDisabled}
          aria-label={selectAllLabel}
        />
        <span>{countLabel}</span>
      </label>
      {compact && showActions && (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="shrink-0"
          aria-label={clearLabel}
          title={clearLabel}
          onClick={clear}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
      {showActions && (
        <span
          className={cn(
            'ml-auto flex items-center',
            compact ? 'shrink-0 gap-0.5' : 'flex-wrap gap-2'
          )}
        >
          {!compact && (
            <Button type="button" size="sm" variant="outline" onClick={clear}>
              <X className="mr-1 h-4 w-4" aria-hidden="true" />
              {clearLabel}
            </Button>
          )}
          {children}
        </span>
      )}
    </div>
  );
}

'use client';

/**
 * SelectionBar — the bar above a list while rows are selected (ADR-259).
 *
 * Exact count, a « select every row of this page » checkbox that states the
 * partial state natively (`indeterminate`), a clear, and the actions the
 * caller composes as children — bulk destruction SOLID red at the toolbar
 * geometry (ADR-207). Strings come translated from the caller (ADR-206). The
 * row checkboxes live in the list; this bar only reads the selection.
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
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
}: SelectionBarProps) {
  const allRef = useRef<HTMLInputElement>(null);

  // `indeterminate` is a DOM property, not an attribute: it is synchronized
  // with the external system (the checkbox element) after each render.
  useEffect(() => {
    if (allRef.current) allRef.current.indeterminate = pageState === 'some';
  }, [pageState]);

  return (
    <div
      role="region"
      aria-label={regionLabel}
      className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2"
    >
      <label className="flex h-11 items-center gap-2 text-sm">
        <Checkbox
          ref={allRef}
          checked={pageState === 'all'}
          onChange={() => (pageState === 'all' ? onClear() : onSelectAll())}
          aria-label={selectAllLabel}
        />
        <span>{countLabel}</span>
      </label>
      <span className="ml-auto flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onClear}>
          <X className="mr-1 h-4 w-4" aria-hidden="true" />
          {clearLabel}
        </Button>
        {children}
      </span>
    </div>
  );
}

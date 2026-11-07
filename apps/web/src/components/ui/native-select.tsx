'use client';

/**
 * NativeSelect — the platform's own list, drawn as a field of the page.
 *
 * A phone's picker is the one its owner knows, so the control stays native. What it takes from
 * `Input` is everything around it: the label and its gap, the height, the ground, the corners and
 * the text, so a form reads as one column instead of two kinds of field. With neither a label nor
 * an error it is the control alone, for a line that holds it beside something else.
 */
import * as React from 'react';

import { cn } from '@/lib/utils';

import { FieldFrame, useFieldA11y } from './field';

export interface NativeSelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

const NativeSelect = React.forwardRef<HTMLSelectElement, NativeSelectProps>(
  ({ className, label, error, id, 'aria-describedby': describedBy, ...props }, ref) => {
    const { fieldId, errorId, hasError, controlProps } = useFieldA11y({ id, error, describedBy });
    const control = (
      <select
        ref={ref}
        className={cn(
          'block h-10 w-full rounded-lg border border-input bg-[color:var(--lia-field-background,var(--color-background))] px-3 text-base shadow-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:border-primary hover:border-primary/50 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
          hasError && 'border-destructive focus-visible:ring-destructive',
          className
        )}
        {...controlProps}
        {...props}
      />
    );
    if (!label && !error) return control;
    return (
      <FieldFrame label={label} fieldId={fieldId} error={error} errorId={errorId}>
        {control}
      </FieldFrame>
    );
  }
);
NativeSelect.displayName = 'NativeSelect';

export { NativeSelect };

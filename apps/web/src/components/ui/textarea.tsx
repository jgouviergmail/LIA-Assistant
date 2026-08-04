'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { FieldFrame, useFieldA11y } from './field';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, id, 'aria-describedby': describedBy, ...props }, ref) => {
    const { fieldId, errorId, hasError, controlProps } = useFieldA11y({ id, error, describedBy });

    return (
      <FieldFrame label={label} fieldId={fieldId} error={error} errorId={errorId}>
        <textarea
          className={cn(
            'flex min-h-[80px] w-full rounded-lg border border-input bg-background px-3 py-2 text-base shadow-sm transition-all duration-200 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:border-primary hover:border-primary/50 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm resize-y',
            hasError &&
              'border-destructive focus-visible:ring-destructive hover:border-destructive/50',
            className
          )}
          ref={ref}
          {...controlProps}
          {...props}
        />
      </FieldFrame>
    );
  }
);
Textarea.displayName = 'Textarea';

export { Textarea };

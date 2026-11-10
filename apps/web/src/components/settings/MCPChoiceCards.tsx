'use client';

import { useId } from 'react';
import type { LucideIcon } from '@/lib/icons';

import { cn } from '@/lib/utils';

export interface MCPChoice<V extends string> {
  value: V;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Why this choice is not offered here; the card stays visible, disabled, saying it. */
  unavailable?: string | null;
}

interface Props<V extends string> {
  legend: string;
  hint?: string;
  value: V;
  choices: readonly MCPChoice<V>[];
  onChange: (value: V) => void;
  /**
   * A choice is being applied: the group says so and the caller ignores another
   * one. Never `disabled` — it would blur the focused radio to <body>, and the alert
   * opened from it could not hand the focus back.
   */
  busy?: boolean;
}

/**
 * One MCP setting as radio cards (spec 2026-10-30 § 1-3).
 *
 * Native radios inside a fieldset — the group semantics and the arrow keys come from
 * the browser, as on the exchange-rhythm screen. A choice the page may not offer here
 * stays visible and disabled with its reason, never hidden: a person who looks for it
 * learns why it is not there.
 */
export function MCPChoiceCards<V extends string>({
  legend,
  hint,
  value,
  choices,
  onChange,
  busy = false,
}: Props<V>) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <fieldset aria-busy={busy} aria-describedby={hintId} className="min-w-0">
      <legend className="mb-1 text-sm font-medium text-foreground">{legend}</legend>
      {hint && (
        <p id={hintId} className="mb-3 text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-3">
        {choices.map(choice => {
          const Icon = choice.icon;
          const selected = value === choice.value;
          const labelId = `${id}-${choice.value}-label`;
          const descriptionId = `${id}-${choice.value}-description`;
          return (
            <label
              key={choice.value}
              className={cn(
                'flex min-w-0 cursor-pointer flex-col gap-1.5 rounded-lg border-2 p-3 transition-all hover:bg-accent',
                'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background',
                'has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60',
                selected ? 'border-primary bg-primary/5' : 'border-border bg-background'
              )}
            >
              <input
                type="radio"
                name={id}
                value={choice.value}
                checked={selected}
                disabled={Boolean(choice.unavailable)}
                onChange={() => onChange(choice.value)}
                aria-labelledby={labelId}
                aria-describedby={descriptionId}
                className="sr-only"
              />
              <span className="flex items-center gap-2">
                <Icon
                  className={cn(
                    'h-4 w-4 shrink-0',
                    selected ? 'text-primary' : 'text-muted-foreground'
                  )}
                  aria-hidden="true"
                />
                <span
                  id={labelId}
                  className={cn(
                    'text-sm font-medium break-words',
                    selected ? 'text-primary' : 'text-foreground'
                  )}
                >
                  {choice.label}
                </span>
              </span>
              <span id={descriptionId} className="text-xs text-muted-foreground">
                {choice.unavailable ?? choice.description}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

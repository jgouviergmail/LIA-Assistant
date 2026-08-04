'use client';

/**
 * Shared form-field plumbing for the labelled control primitives.
 *
 * `Input` and `Textarea` had the same three concerns copied into each file: a
 * generated id, a hand-written `<label>` whose classes duplicated `Label`, and
 * an error message rendered as a bare paragraph. Copying them meant fixing them
 * twice — and the error message was never wired to the control at all, so the
 * rejection was visible but not announced.
 *
 * This module owns the contract once:
 *
 *  - **Identity** comes from `useId`, never from the label text. A label-derived
 *    id collides whenever two fields share a label (routine in the settings
 *    screens) and changes with the active locale.
 *  - **Invalidity** is programmatic (`aria-invalid`), not just a red border.
 *  - **The message is attached** through `aria-describedby` and announced with
 *    `role="alert"`, and it never evicts a description the caller already set.
 */

import * as React from 'react';

import { Label } from './label';

/** What a labelled control needs to resolve its accessibility wiring. */
export interface UseFieldA11yOptions {
  /** Caller-supplied id; when omitted a stable generated one is used. */
  id?: string;
  /** Error message, if the field is currently rejected. */
  error?: string;
  /** Description ids the caller already points the control at. */
  describedBy?: string;
}

/** The resolved wiring: ids for the markup, ARIA props for the control. */
export interface FieldA11y {
  /** Id carried by the control and targeted by the label's `htmlFor`. */
  fieldId: string;
  /** Id of the error paragraph; referenced only while an error is shown. */
  errorId: string;
  /** Whether an error message is actually present (an empty string is not). */
  hasError: boolean;
  /** Spread onto the native control element. */
  controlProps: {
    id: string;
    'aria-invalid'?: true;
    'aria-describedby'?: string;
  };
}

/**
 * Resolve the id and ARIA wiring of a labelled form control.
 *
 * Args:
 *   options: The caller's id, error message and existing description ids.
 *
 * Returns:
 *   The ids to render and the props to spread onto the control.
 */
export function useFieldA11y({ id, error, describedBy }: UseFieldA11yOptions): FieldA11y {
  const generatedId = React.useId();
  const fieldId = id ?? generatedId;
  const errorId = `${fieldId}-error`;
  const hasError = Boolean(error);

  // A hint the caller attached ("must contain an @") stays useful once the
  // field is rejected, so the two descriptions are additive rather than
  // exclusive. `undefined` — not an empty string — when there is nothing to
  // point at, so React omits the attribute entirely.
  const description = [describedBy, hasError ? errorId : null].filter(Boolean).join(' ');

  return {
    fieldId,
    errorId,
    hasError,
    controlProps: {
      id: fieldId,
      'aria-invalid': hasError ? true : undefined,
      'aria-describedby': description || undefined,
    },
  };
}

/** Layout shell shared by every labelled control. */
export interface FieldFrameProps {
  /** Visible label text; omitted when the caller names the control otherwise. */
  label?: string;
  /** Id of the control the label points at. */
  fieldId: string;
  /** Error message to announce, if any. */
  error?: string;
  /** Id given to the error paragraph. */
  errorId: string;
  /** The control itself. */
  children: React.ReactNode;
}

/**
 * Render the label / control / error stack shared by the field primitives.
 *
 * Uses the `Label` primitive rather than a hand-written `<label>`: the classes
 * were already identical, and Radix's label additionally suppresses the text
 * selection that a double click on a label otherwise triggers.
 *
 * Args:
 *   props: Label text, the control's id, the error state and the control.
 *
 * Returns:
 *   The wrapped field.
 */
export function FieldFrame({ label, fieldId, error, errorId, children }: FieldFrameProps) {
  return (
    // `space-y-3`: the app-wide label->control gap. Arbitrated on real
    // screenshots (2026-08-05) AFTER fixing the Label primitive to `block` —
    // with the default inline label, margins were computed but never rendered,
    // which is why earlier recalibrations were invisible on screen.
    <div className="w-full space-y-3">
      {label && <Label htmlFor={fieldId}>{label}</Label>}
      {children}
      {error && (
        // `role="alert"` so the reason surfaces the moment the field is
        // rejected, without the user having to go looking for it.
        <p id={errorId} role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

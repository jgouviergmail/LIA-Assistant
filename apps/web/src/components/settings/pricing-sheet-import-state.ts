'use client';

/**
 * The import dialog's state machine, kept out of the view.
 *
 * Extracted because the component that held it crossed the complexity ratchet:
 * a screen that decides whether to rewrite every price in the product should be
 * readable, and mixing "what happens when the file changes" with "what the
 * reader sees" is how a screen stops being readable.
 *
 * Two guards live here rather than in the markup:
 *
 * - choosing a new file **invalidates the previous verdict**. Leaving the old
 *   plan on screen would let someone apply a diff built from a file they had
 *   already replaced.
 * - a second click while the first apply is in flight does nothing. The guard
 *   is a ref, not state: it has to hold within the same tick the double click
 *   produces, before React has re-rendered.
 */

import { useCallback, useRef, useState } from 'react';

import type { PricingSheetImportReport, PricingSheetPlan } from '@/hooks/useLLMPricingSheet';

export interface PricingSheetImportState {
  /** The workbook currently under review, if any. */
  file: File | null;
  /** The plan the last preview returned. */
  report: PricingSheetImportReport | null;
  /** What the apply actually wrote, once it has. */
  appliedReport: PricingSheetImportReport | null;
  /** A refusal or a network failure, in the words the server used. */
  error: string | null;
  /** True while an apply is in flight, so the control can say so. */
  inFlight: boolean;
  /** The plan under review, if a preview has returned one. */
  plan: PricingSheetPlan | null;
  /** True when the workbook carries problems that forbid writing. */
  hasIssues: boolean;
  /** True when there is something to write and nothing forbidding it. */
  canApply: boolean;
  chooseFile: (file: File | null) => Promise<void>;
  applyPlan: () => Promise<void>;
}

/**
 * Drive one import from file choice to applied report.
 *
 * Args:
 *   onPreview: Uploads the file and returns the plan, writing nothing.
 *   onApply: Applies the reviewed plan, keyed on its fingerprint.
 *
 * Returns:
 *   The state of the current import and the two transitions that move it.
 */
export function usePricingSheetImportState(
  onPreview: (file: File) => Promise<PricingSheetImportReport>,
  onApply: (file: File, planFingerprint: string) => Promise<PricingSheetImportReport>
): PricingSheetImportState {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<PricingSheetImportReport | null>(null);
  const [appliedReport, setAppliedReport] = useState<PricingSheetImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState(false);
  const applying = useRef(false);

  const chooseFile = useCallback(
    async (chosen: File | null) => {
      setFile(chosen);
      setReport(null);
      setAppliedReport(null);
      setError(null);
      if (!chosen) return;
      try {
        setReport(await onPreview(chosen));
      } catch (cause) {
        // The message is the server's own words — "workbook exceeds the limit"
        // tells the administrator what to do; "an error occurred" does not.
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    },
    [onPreview]
  );

  const applyPlan = useCallback(async () => {
    if (applying.current || !file || !report?.plan.is_applicable) return;
    applying.current = true;
    setInFlight(true);
    setError(null);
    try {
      setAppliedReport(await onApply(file, report.plan.plan_fingerprint));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      applying.current = false;
      setInFlight(false);
    }
  }, [file, report, onApply]);

  // Derived here rather than in the view: they are statements ABOUT the state,
  // and computing them in the markup is what pushed that component past the
  // complexity ratchet.
  const plan = report?.plan ?? null;
  const hasIssues = (plan?.issues.length ?? 0) > 0;
  const canApply =
    plan !== null &&
    plan.is_applicable &&
    plan.changes.some(change => change.action !== 'unchanged') &&
    appliedReport === null;

  return {
    file,
    report,
    appliedReport,
    error,
    inFlight,
    plan,
    hasIssues,
    canApply,
    chooseFile,
    applyPlan,
  };
}

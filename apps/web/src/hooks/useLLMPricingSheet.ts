import { useCallback, useState } from 'react';

import { apiEndpointUrl } from '@/lib/api-client';

const ENDPOINT = '/admin/llm/pricing/sheet';

/** Taxonomy code for a workbook problem — mirrors the backend `IssueCode`. */
export type SheetIssueCode =
  | 'not_a_workbook'
  | 'archive_too_large'
  | 'schema_version_mismatch'
  | 'sheet_missing'
  | 'column_missing'
  | 'too_many_rows'
  | 'formula_rejected'
  | 'not_a_number'
  | 'not_a_boolean'
  | 'not_a_time'
  | 'too_many_decimals'
  | 'out_of_range'
  | 'value_not_in_referential'
  | 'key_missing'
  | 'duplicate_key'
  | 'provider_immutable'
  | 'row_changed_since_export'
  | 'creation_needs_template'
  | 'creation_field_missing';

/** What an import would do to one model. */
export type SheetChangeAction =
  | 'create'
  | 'update'
  | 'deactivate'
  | 'reactivate'
  | 'unchanged';

export interface SheetIssue {
  code: SheetIssueCode;
  sheet: string | null;
  cell: string | null;
  column: string | null;
  params: Record<string, string>;
}

export interface SheetFieldChange {
  field: string;
  before: string | null;
  after: string | null;
}

export interface SheetModelChange {
  model_name: string;
  action: SheetChangeAction;
  fields: SheetFieldChange[];
  slots_before: number;
  slots_after: number;
  row_number: number | null;
}

export interface PricingSheetPlan {
  plan_fingerprint: string;
  counts: Partial<Record<SheetChangeAction, number>>;
  changes: SheetModelChange[];
  issues: SheetIssue[];
  is_applicable: boolean;
  pricing_changes: string[];
}

export interface PricingSheetImportReport {
  applied: boolean;
  plan: PricingSheetPlan;
  created: string[];
  updated: string[];
  deactivated: string[];
  reactivated: string[];
  unchanged: number;
}

interface UseLLMPricingSheet {
  /** Download the catalogue as a workbook. */
  exportSheet: () => void;
  /** Diff an edited workbook without writing anything. */
  preview: (file: File) => Promise<PricingSheetImportReport>;
  /** Apply the plan the administrator reviewed, and only that one. */
  apply: (file: File, planFingerprint: string) => Promise<PricingSheetImportReport>;
  /** True while an upload is in flight. */
  busy: boolean;
}

/**
 * Workbook export and import for the LLM pricing administration (ADR-228).
 *
 * The import is two-phase on purpose: `preview` writes nothing and returns the
 * plan, `apply` re-sends the SAME file with the fingerprint of the plan that
 * was reviewed. The backend re-derives the plan and refuses a different one, so
 * a catalogue that moved between the two calls cannot be written over blindly.
 *
 * Uploads go through a raw `fetch` because `apiClient` forces a JSON
 * content-type and a multipart body needs the browser to set its own boundary —
 * same reason as the plugin and skill importers.
 */
export function useLLMPricingSheet(): UseLLMPricingSheet {
  const [busy, setBusy] = useState(false);

  const exportSheet = useCallback(() => {
    // A top-level navigation, not a blob: the browser streams the file to disk
    // and the session cookie rides along on a same-site GET.
    window.open(apiEndpointUrl(`${ENDPOINT}/export.xlsx`), '_blank');
  }, []);

  const upload = useCallback(
    async (file: File, query: string): Promise<PricingSheetImportReport> => {
      const formData = new FormData();
      formData.append('file', file);

      setBusy(true);
      try {
        const response = await fetch(apiEndpointUrl(`${ENDPOINT}/import?${query}`), {
          method: 'POST',
          credentials: 'include',
          body: formData,
        });

        if (!response.ok) {
          // A refusal carries a reason; swallowing it into an empty report
          // would leave the administrator staring at a screen that says
          // nothing happened when in fact nothing was allowed to.
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail || `Import failed (${response.status})`);
        }
        return (await response.json()) as PricingSheetImportReport;
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const preview = useCallback(
    (file: File) => upload(file, 'dry_run=true'),
    [upload]
  );

  const apply = useCallback(
    (file: File, planFingerprint: string) =>
      upload(
        file,
        `dry_run=false&plan_fingerprint=${encodeURIComponent(planFingerprint)}`
      ),
    [upload]
  );

  return { exportSheet, preview, apply, busy };
}

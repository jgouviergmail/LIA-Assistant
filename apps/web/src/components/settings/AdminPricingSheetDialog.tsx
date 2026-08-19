'use client';

/**
 * Import dialog for the LLM pricing workbook (ADR-228).
 *
 * The screen where an administrator decides whether to change every price in
 * the product, so it is built to be read before it is clever:
 *
 * - **problems come first**, each pointing at the sheet and cell that carries
 *   it — "row 42, column M" is the difference between a report someone can act
 *   on and one they can only stare at;
 * - **only what moves is shown.** Untouched rows are counted, never listed:
 *   124 lines of "nothing happened" hide the three that matter;
 * - **applying is impossible until a plan has been reviewed**, and it carries
 *   that plan's fingerprint, so a catalogue that moved in between is refused
 *   rather than written over.
 *
 * Kept in its own component — `AdminLLMPricingSection` is already 1600 lines —
 * and split into a state hook plus three sections, so no single function has to
 * hold the whole screen at once.
 */

import { useRef } from 'react';

import type { LucideIcon } from 'lucide-react';
import {
  AlertTriangle,
  FileSpreadsheet,
  Pencil,
  Plus,
  Power,
  PowerOff,
  Upload,
} from 'lucide-react';

import type {
  PricingSheetImportReport,
  PricingSheetPlan,
  SheetIssue,
  SheetModelChange,
} from '@/hooks/useLLMPricingSheet';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { usePricingSheetImportState } from '@/components/settings/pricing-sheet-import-state';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

const ACCEPTED = '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** Anything the reader may translate, resolved by the caller. */
type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * Order the preview reads in — created, edited, brought back, retired — each
 * with the glyph that says which it is at a glance.
 */
const ACTION_ORDER: ReadonlyArray<{ action: string; icon: LucideIcon }> = [
  { action: 'create', icon: Plus },
  { action: 'update', icon: Pencil },
  { action: 'reactivate', icon: Power },
  { action: 'deactivate', icon: PowerOff },
];

export interface AdminPricingSheetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPreview: (file: File) => Promise<PricingSheetImportReport>;
  onApply: (file: File, planFingerprint: string) => Promise<PricingSheetImportReport>;
  busy: boolean;
  /** Required: every route is localized, so a caller always has one. */
  lng: Language;
}

/** One problem, with the coordinates that make it fixable. */
function IssueLine({ issue, label }: { issue: SheetIssue; label: string }) {
  const where = [issue.sheet, issue.cell].filter(Boolean).join(' · ');
  return (
    <li className="flex flex-col gap-0.5 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm sm:flex-row sm:items-baseline sm:gap-2">
      <span className="font-medium text-destructive">{label}</span>
      {where && <span className="text-xs text-muted-foreground">{where}</span>}
    </li>
  );
}

/**
 * One model's changes.
 *
 * Stacks on a phone and lines up from `sm`: a before/after table would need a
 * horizontal scroll on 390px, and a diff you have to scroll sideways is a diff
 * nobody checks.
 */
function ChangeLine({ change }: { change: SheetModelChange }) {
  return (
    <li className="space-y-1 rounded-md border border-border/40 px-3 py-2">
      {/* The group this row sits in is already titled with the action, so the
          row states its identity, not its category. A badge repeating the
          heading on every line is noise the reader has to skip. */}
      <p className="font-medium">{change.model_name}</p>
      {change.fields.length > 0 && (
        <dl className="space-y-0.5 text-sm">
          {change.fields.map(field => (
            <div key={field.field} className="flex flex-col gap-x-2 sm:flex-row sm:items-baseline">
              <dt className="text-xs text-muted-foreground sm:w-52 sm:shrink-0">{field.field}</dt>
              <dd className="flex flex-wrap items-baseline gap-2">
                <span className="text-muted-foreground line-through">{field.before ?? '—'}</span>
                <span aria-hidden="true">→</span>
                <span className="font-medium">{field.after ?? '—'}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}
      {change.slots_before !== change.slots_after && (
        <p className="text-xs text-muted-foreground">
          {change.slots_before} → {change.slots_after}
        </p>
      )}
    </li>
  );
}

/** Everything that forbids applying, listed before anything else. */
function IssueSection({ plan, t }: { plan: PricingSheetPlan; t: Translate }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">
        {t('settings.admin.llm.sheet.issues_title', { count: plan.issues.length })}
      </h3>
      <ul className="space-y-1.5">
        {plan.issues.map((issue, index) => (
          <IssueLine
            key={`${issue.code}-${issue.cell ?? index}`}
            issue={issue}
            label={t(`settings.admin.llm.sheet.issue.${issue.code}`, issue.params)}
          />
        ))}
      </ul>
    </section>
  );
}

/** The diff itself, grouped by nature and collapsible. */
function ChangeSection({ plan, t }: { plan: PricingSheetPlan; t: Translate }) {
  const moved = plan.changes.filter(change => change.action !== 'unchanged');
  return (
    <section className="space-y-2">
      {moved.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('settings.admin.llm.sheet.no_change')}</p>
      )}
      {ACTION_ORDER.map(({ action, icon }) => {
        const rows = moved.filter(change => change.action === action);
        if (rows.length === 0) return null;
        return (
          <SettingsDisclosure
            key={action}
            icon={icon}
            title={t(`settings.admin.llm.sheet.action.${action}`)}
            badge={String(rows.length)}
            defaultOpen
          >
            <ul className="space-y-2 pb-2">
              {rows.map(change => (
                <ChangeLine key={change.model_name} change={change} />
              ))}
            </ul>
          </SettingsDisclosure>
        );
      })}
      <p className="text-sm text-muted-foreground">
        {t('settings.admin.llm.sheet.unchanged_count', { count: plan.counts.unchanged ?? 0 })}
      </p>
    </section>
  );
}

/** What the import actually wrote — named, never merely "done". */
function AppliedSection({
  report,
  t,
}: {
  report: PricingSheetImportReport;
  t: Translate;
}) {
  return (
    <section className="space-y-1 rounded-md border border-success/40 bg-success/5 px-3 py-2">
      <h3 className="text-sm font-semibold">{t('settings.admin.llm.sheet.applied_title')}</h3>
      <p className="text-sm text-muted-foreground">
        {t('settings.admin.llm.sheet.applied_summary', {
          created: report.created.length,
          updated: report.updated.length,
          deactivated: report.deactivated.length,
          reactivated: report.reactivated.length,
        })}
      </p>
    </section>
  );
}

/** The file picker: a hidden native input behind a control that matches the app. */
function FilePicker({
  fileName,
  onChoose,
  t,
}: {
  fileName: string | null;
  onChoose: (file: File | null) => void;
  t: Translate;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      {/* The same shape the plugin and skill importers use: a hidden input
          carrying its own accessible name, driven by a real Button. The
          browser's native file control cannot be styled and looks like nothing
          else in the product — and a visible label linked by `htmlFor` would
          not satisfy the jsx-a11y rule anyway, which cannot follow that link
          across a component boundary. */}
      <input
        ref={input}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        data-testid="pricing-sheet-file-input"
        aria-label={t('settings.admin.llm.sheet.choose_file')}
        onChange={event => onChoose(event.target.files?.[0] ?? null)}
      />
      <Button type="button" variant="outline" onClick={() => input.current?.click()}>
        <FileSpreadsheet className="mr-2 h-4 w-4" aria-hidden="true" />
        {t('settings.admin.llm.sheet.choose_file')}
      </Button>
      {fileName && <span className="truncate text-sm text-muted-foreground">{fileName}</span>}
    </div>
  );
}

/** The one control that writes anything. */
function ApplyButton({
  working,
  onApply,
  t,
}: {
  working: boolean;
  onApply: () => void;
  t: Translate;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
      <Button
        type="button"
        variant="default"
        // `aria-disabled` plus the guard in the handler, never `disabled`, and
        // never `isLoading` — which sets `disabled` natively AND swaps the
        // children for a spinner. Both would cost the keyboard user their
        // place: the browser blurs a disabled control and drops it from the tab
        // order, and a control that loses its label loses its accessible name
        // in the middle of the action it is announcing.
        aria-disabled={working}
        onClick={onApply}
      >
        {working ? (
          <LoadingSpinner size="default" className="mr-2" aria-hidden="true" />
        ) : (
          <Upload className="mr-2 h-4 w-4" aria-hidden="true" />
        )}
        {t('settings.admin.llm.sheet.apply')}
      </Button>
    </div>
  );
}

export function AdminPricingSheetDialog({
  open,
  onOpenChange,
  onPreview,
  onApply,
  busy,
  lng,
}: AdminPricingSheetDialogProps) {
  const { t } = useTranslation(lng, 'translation');
  const state = usePricingSheetImportState(onPreview, onApply);
  const { plan, appliedReport, error, hasIssues, canApply } = state;
  const working = busy || state.inFlight;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" aria-hidden="true" />
            {t('settings.admin.llm.sheet.import_title')}
          </DialogTitle>
          <DialogDescription>{t('settings.admin.llm.sheet.import_description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4" aria-busy={working}>
          <FilePicker
            fileName={state.file?.name ?? null}
            onChoose={chosen => void state.chooseFile(chosen)}
            t={t}
          />

          {error && (
            <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}

          {plan && hasIssues && <IssueSection plan={plan} t={t} />}
          {plan && !hasIssues && <ChangeSection plan={plan} t={t} />}
          {appliedReport && <AppliedSection report={appliedReport} t={t} />}

          {canApply && (
            <ApplyButton working={working} onApply={() => void state.applyPlan()} t={t} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

'use client';

import { AlertTriangle, CalendarClock, CheckCircle2, Database } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { SettingsDisclosure } from './SettingsDisclosure';
import { capabilityProvenanceTone } from '@/lib/status-tone';
import { formatLocalDateInput } from '@/lib/date-format';
import type { CatalogueStatus } from '@/lib/actions/settings-actions';

/**
 * What the two vendored public registries say about this catalogue (ADR-244).
 *
 * The correction they drove — 83 rows repaired, 14 retired models deactivated —
 * happened in a migration and left no trace an operator could see. In front of
 * this table the question is always the same: *is this 8 192 a measurement, or
 * the column default nobody ever curated?* The provenance breakdown answers it
 * for the whole catalogue, and the badge on each row answers it per model.
 *
 * Read-only on purpose. Applying a correction stays a reviewed migration, so
 * this panel offers no button that would write: it reports, and says when the
 * snapshot it reports from was taken.
 */
interface CatalogueStatusPanelProps {
  status: CatalogueStatus | null;
  t: (key: string, options?: Record<string, unknown>) => string;
}

/** Order matters: the reader looks for the untrusted rows first. */
const PROVENANCE_ORDER = ['declared', 'imported', 'verified'] as const;

export function CatalogueStatusPanel({ status, t }: CatalogueStatusPanelProps) {
  // No verdict is the absence of a diagnostic, not an error to shout about:
  // the catalogue itself is still perfectly usable without it.
  if (!status) return null;

  // Read defensively: this panel is a DIAGNOSTIC sitting above the catalogue
  // table, and a payload missing a field must leave the diagnostic incomplete,
  // never take the table down with it. Measured: a response without
  // `provenance` threw inside render and unmounted the whole section.
  const provenance = status.provenance ?? {};
  const retiring = status.retiring ?? [];
  const pending = (status.auto ?? 0) + (status.review ?? 0);
  const compared = status.compared ?? 0;
  // `YYYY-MM-DD`, not the browser's locale format: the retirement rows right
  // below print the provider's ISO dates verbatim, and one line reading
  // "8/24/2026" next to "2026-10-23" makes the reader compare two calendars.
  const snapshotDate = status.snapshot_generated_at
    ? formatLocalDateInput(new Date(status.snapshot_generated_at))
    : null;

  return (
    <div className="rounded-lg border border-border bg-muted/20 px-4 py-3 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
          <Database className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('settings.admin.llm.catalogue.title')}
        </span>

        {PROVENANCE_ORDER.filter(key => (provenance[key] ?? 0) > 0).map(key => (
          <Badge key={key} variant={capabilityProvenanceTone(key)}>
            {t(`settings.admin.llm.catalogue.provenance.${key}`)}: {provenance[key]}
          </Badge>
        ))}

        {pending === 0 ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-hidden="true" />
            {t(
              compared > 1
                ? 'settings.admin.llm.catalogue.aligned_plural'
                : 'settings.admin.llm.catalogue.aligned',
              { total: compared }
            )}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <AlertTriangle className="h-3.5 w-3.5 text-warning" aria-hidden="true" />
            {t('settings.admin.llm.catalogue.pending', {
              auto: status.auto,
              review: status.review,
            })}
          </span>
        )}
      </div>

      {retiring.length > 0 && (
        <SettingsDisclosure
          icon={CalendarClock}
          title={t('settings.admin.llm.catalogue.retiring_summary')}
          badge={retiring.length}
          description={t('settings.admin.llm.catalogue.retiring_description')}
        >
          <ul className="space-y-1 pt-1">
            {retiring.map(entry => (
              <li
                key={entry.model_name}
                className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
              >
                <code className="font-mono text-foreground">{entry.model_name}</code>
                <Badge variant={entry.state === 'retired' ? 'warning' : 'secondary'}>
                  {t(`settings.admin.llm.catalogue.state.${entry.state}`)}
                </Badge>
                {entry.deprecation_date && <span>{entry.deprecation_date}</span>}
                <span className="italic" title={t('settings.admin.llm.catalogue.seen_by_help')}>
                  {entry.seen_by.join(', ')}
                </span>
              </li>
            ))}
          </ul>
        </SettingsDisclosure>
      )}

      {snapshotDate && (
        <p className="text-[11px] text-muted-foreground">
          {t('settings.admin.llm.catalogue.snapshot', { date: snapshotDate })}
        </p>
      )}
    </div>
  );
}

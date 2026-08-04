'use client';

/**
 * "Why does LIA think this?" — the signals behind one belief, and the way to
 * correct it.
 *
 * A journal entry states a conclusion; a memory states a fact. Both are
 * injected into prompts, and until now neither could be argued with: the entry
 * showed a confidence dot and two counters ("✓3 / ✗1") that answered *how
 * many* and never *which*. Three confirmations you cannot see are not an
 * explanation.
 *
 * Three rules, and each of them is why the block exists at all:
 *
 * - **folded, and unmounted while folded.** The query fires when the reader
 *   asks, not on a list of forty entries. `SettingsDisclosure` renders its
 *   children only while open, which is what makes that free;
 * - **a deleted source is a TOMBSTONE, never a resurrection.** The backend
 *   nulls the pointer and keeps the date; this shows "the conversation is
 *   gone, on that day" and no text. Reproducing what the reader deleted would
 *   make their deletion not a deletion;
 * - **the cap is stated.** The trail is bounded server-side, so the block says
 *   so rather than letting "5 signals" read as "all of them" (ADR-184: an
 *   enforced bound the reader cannot see is a trap).
 *
 * Shared by journals and memories on purpose: two surfaces answering the same
 * question must not drift into two vocabularies. The caller supplies only WHERE
 * to read and WHAT to correct.
 */

import { useState } from 'react';
import { HelpCircle, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { useApiQuery } from '@/hooks/useApiQuery';
import { formatInstant } from '@/lib/format-instant';

export interface ProvenanceReference {
  id: string;
  /** `origin`, `evidence` or `contradiction`. */
  outcome: string;
  captured_at: string;
  conversation_id: string | null;
  /** Live quotation of the source turn; null for a tombstone. */
  excerpt: string | null;
  is_tombstone: boolean;
}

export interface ProvenancePayload {
  references: ProvenanceReference[];
  total: number;
  /** The cap the trail is kept at — published, never applied in silence. */
  kept_at_most: number;
}

export interface ProvenanceDisclosureProps {
  /** Endpoint of this belief's provenance, e.g. `/journals/{id}/provenance`. */
  endpoint: string;
  /** BCP-47 locale for dates. */
  locale: string;
  /**
   * Open the correction form for this belief.
   *
   * Correcting is the point: provenance without a way to act on what it
   * reveals is a read-only apology. Absent on a surface with no editor, and
   * the control then does not render rather than leading nowhere.
   */
  onCorrect?: () => void;
}

/** Outcomes this build can name. An unknown one renders raw, never as a key. */
const KNOWN_OUTCOMES = new Set(['origin', 'evidence', 'contradiction']);

const OUTCOME_TONE: Record<string, string> = {
  origin: 'bg-primary/10 text-primary',
  evidence: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  contradiction: 'bg-orange-500/10 text-orange-700 dark:text-orange-300',
};

export function ProvenanceDisclosure({ endpoint, locale, onCorrect }: ProvenanceDisclosureProps) {
  // NOTE: every read below is optional-chained. This block renders INSIDE
  // other panels (a journal entry, a memory, an interest), so a payload whose
  // shape surprises it must degrade to "nothing recorded" — never throw and
  // take the surrounding list down with it through the error boundary.
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const { data, loading, error } = useApiQuery<ProvenancePayload>(endpoint, {
    componentName: 'ProvenanceDisclosure',
    enabled: open,
  });

  // Derived from the ABSENCE of data, never from `error`: a refetch clears the
  // error, and a spinner keyed on it would unmount the list mid-refresh.
  const firstLoad = data === undefined && loading;

  return (
    <SettingsDisclosure
      icon={HelpCircle}
      title={t('provenance.title')}
      onOpenChange={setOpen}
      // A phone does not get this block: it is dense by nature — a list of
      // dated signals, or the six coefficients behind a weight — and it pushed
      // the thing the reader came for off a small screen. Hidden in CSS rather
      // than unmounted: the disclosure renders its children only when open, so
      // a closed one already costs no request, and a JS-driven variant would
      // make the server and the first client paint disagree.
      className="mt-2 hidden sm:block"
    >
      {firstLoad ? (
        <div className="flex justify-center py-4">
          <LoadingSpinner className="h-4 w-4" />
        </div>
      ) : error && !data ? (
        // Checked BEFORE emptiness: "no signal" on a failed fetch tells the
        // reader LIA concluded this out of nothing, which may be false.
        <p role="alert" className="text-xs text-destructive">
          {t('provenance.error')}
        </p>
      ) : !data?.references?.length ? (
        <p className="text-xs italic text-muted-foreground">{t('provenance.empty')}</p>
      ) : (
        <ul className="space-y-2" role="list">
          {data.references.map(reference => (
            <li
              key={reference.id}
              className="rounded-md border border-border/40 bg-card/40 px-2.5 py-1.5"
            >
              <p className="flex flex-wrap items-center gap-1.5">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                    OUTCOME_TONE[reference.outcome] ?? OUTCOME_TONE.origin
                  }`}
                >
                  {KNOWN_OUTCOMES.has(reference.outcome)
                    ? t(`provenance.outcome.${reference.outcome}`)
                    : reference.outcome}
                </span>
                <time
                  dateTime={reference.captured_at}
                  className="text-[11px] tabular-nums text-muted-foreground"
                >
                  {formatInstant(reference.captured_at, locale)}
                </time>
              </p>
              {reference.is_tombstone ? (
                // Full `muted-foreground`: at this size a diluted /80 falls
                // under the 4.5:1 AA floor.
                <p className="mt-0.5 text-xs italic text-muted-foreground">
                  {t('provenance.source_deleted')}
                </p>
              ) : (
                reference.excerpt && (
                  // Plain React children: this echoes what a human wrote.
                  <p className="mt-0.5 line-clamp-3 text-xs text-foreground/90">
                    {reference.excerpt}
                  </p>
                )
              )}
            </li>
          ))}
        </ul>
      )}

      {/* The cap must be a number before it is stated: this line exists to say
          "capped at N", and "capped at undefined" would be worse than silence.
          Same defensive reading as everything else in this block. */}
      {data && data.total > 0 && typeof data.kept_at_most === 'number' && (
        <p className="mt-2 text-[11px] tabular-nums text-muted-foreground">
          {t('provenance.count', { total: data.total, cap: data.kept_at_most })}
        </p>
      )}

      {onCorrect && (
        <button
          type="button"
          onClick={onCorrect}
          className="mt-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border/60 px-2.5 text-xs font-medium text-foreground/90 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
          {t('provenance.correct')}
        </button>
      )}
    </SettingsDisclosure>
  );
}

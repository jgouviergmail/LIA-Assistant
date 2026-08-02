'use client';

/**
 * Merge two relationships into one — the correction folding cannot make.
 *
 * The CRM groups relationships by folded name, which catches accents, case and
 * spacing. It cannot know that "0612345678" and "Alice Vernier" are one person,
 * or that "Papa" is "Jean Dupont": that is a judgement, and only the user can
 * make it. So the merge is offered here, manually, and never proposed.
 *
 * What was merged is SHOWN, with its own undo. A merge nobody can see is a
 * merge nobody can correct — and nothing is rewritten in the sources, so
 * undoing one restores exactly the two cards that existed before.
 */

import { useCallback, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link2, Undo2 } from 'lucide-react';

interface RelationMergePanelProps {
  /** The relationship currently open — the merge TARGET. */
  displayName: string;
  /** Relationships already merged into it, as they were displayed before. */
  mergedFrom: string[];
  /** Every relationship of the overview (the open one is filtered out here). */
  candidates: string[];
  /** A write is in flight — the panel announces it, it does not unmount. */
  busy: boolean;
  onMerge: (source: string) => Promise<{ ok: boolean }>;
  onSplit: (source: string) => Promise<{ ok: boolean }>;
}

export function RelationMergePanel({
  displayName,
  mergedFrom,
  candidates,
  busy,
  onMerge,
  onSplit,
}: RelationMergePanelProps) {
  const { t } = useTranslation();
  // Generated, not hard-coded: two panels on one page would otherwise share an
  // id, and a duplicate id makes `htmlFor` bind the label to whichever select
  // the browser finds first — the wrong one, silently.
  const selectId = useId();
  const [picked, setPicked] = useState('');
  const [failed, setFailed] = useState(false);

  // Never offer the open relationship: merging it with itself has no meaning
  // and the API refuses it. Also drop what is already merged in.
  const selectable = candidates.filter(
    name => name !== displayName && !mergedFrom.includes(name)
  );

  const submit = useCallback(async () => {
    // The GUARD is here, not on the attribute: `aria-disabled` keeps the
    // button in the tab order (a `disabled` one blurs and drops the keyboard
    // user back on <body>), so the handler is what prevents a double submit.
    if (busy || !picked) return;
    setFailed(false);
    const { ok } = await onMerge(picked);
    if (ok) {
      setPicked('');
    } else {
      setFailed(true);
    }
  }, [busy, picked, onMerge]);

  const undo = useCallback(
    async (name: string) => {
      if (busy) return;
      setFailed(false);
      const { ok } = await onSplit(name);
      if (!ok) setFailed(true);
    },
    [busy, onSplit]
  );

  return (
    <section
      role="group"
      aria-label={t('relations.merge_title')}
      aria-busy={busy}
      className="rounded-xl border border-border bg-muted/20 p-4"
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Link2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('relations.merge_title')}
      </h3>
      <p className="mt-1 text-xs text-muted-foreground">{t('relations.merge_help')}</p>

      {selectable.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">{t('relations.merge_no_candidate')}</p>
      ) : (
        // Column on a phone, row from `sm` up: a select and its action button
        // side by side below ~380px would each be too narrow to read.
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="sr-only" htmlFor={selectId}>
            {t('relations.merge_pick')}
          </label>
          <select
            id={selectId}
            value={picked}
            onChange={event => setPicked(event.target.value)}
            className="min-h-11 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex-1"
          >
            <option value="">{t('relations.merge_pick_placeholder')}</option>
            {selectable.map(name => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={submit}
            aria-disabled={busy || !picked}
            className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
          >
            <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
            {t('relations.merge_action')}
          </button>
        </div>
      )}

      {mergedFrom.length > 0 && (
        <div className="mt-4 border-t border-border pt-3">
          <h4 className="text-xs font-medium text-foreground">
            {t('relations.merge_merged_title')}
          </h4>
          <ul className="mt-2 space-y-1">
            {mergedFrom.map(name => (
              <li key={name} className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm text-foreground/90">{name}</span>
                <button
                  type="button"
                  onClick={() => undo(name)}
                  aria-disabled={busy}
                  // Named with the relationship, so a screen reader announces
                  // "undo the merge of Papa" instead of five identical "undo".
                  aria-label={t('relations.merge_undo', { name })}
                  className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
                >
                  <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('relations.merge_undo_short')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {failed && (
        <p role="alert" className="mt-3 text-xs text-destructive">
          {t('relations.merge_failed')}
        </p>
      )}
    </section>
  );
}

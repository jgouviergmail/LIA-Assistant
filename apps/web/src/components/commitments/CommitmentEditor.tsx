'use client';

/**
 * CommitmentEditor — inline correction of a commitment (2026-08-02).
 *
 * The ledger fills itself from conversation, so its wording is only as good as
 * what was heard: a subject comes out garbled, "d'ici vendredi" lands on the
 * wrong Friday. Only those two fields are editable — direction and counterparty
 * describe a DIFFERENT commitment, not a correction.
 *
 * Shared by the two surfaces that show commitments (Settings → Features, and a
 * relation's sheet) so a correction behaves identically wherever it is made.
 */

import { Check, X } from 'lucide-react';
import { useState } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface CommitmentEditorProps {
  lng: Language;
  subject: string;
  /** ISO datetime, or null when the commitment carries no deadline. */
  dueHint: string | null;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: { subject?: string; due_hint?: string | null; clear_due_hint?: boolean }) => void;
}

/** `2026-08-14T09:00:00Z` → `2026-08-14`, the shape `<input type="date">` wants. */
function toDateInputValue(iso: string | null): string {
  if (!iso) return '';
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString().slice(0, 10);
}

export function CommitmentEditor({
  lng,
  subject,
  dueHint,
  saving,
  onCancel,
  onSave,
}: CommitmentEditorProps) {
  const { t } = useTranslation(lng);
  const [draftSubject, setDraftSubject] = useState(subject);
  const [draftDue, setDraftDue] = useState(() => toDateInputValue(dueHint));

  const trimmed = draftSubject.trim();
  // A commitment with no wording says nothing to anyone — the API refuses it
  // too, so the button states the rule rather than letting the request fail.
  const invalid = trimmed.length === 0;
  const unchanged = trimmed === subject.trim() && draftDue === toDateInputValue(dueHint);
  const blocked = saving || invalid || unchanged;

  const submit = () => {
    // `aria-disabled` keeps the button focusable (a `disabled` control loses
    // focus and leaves the tab order mid-interaction), so the guard lives here.
    if (blocked) return;
    const originalDue = toDateInputValue(dueHint);
    const patch: { subject?: string; due_hint?: string | null; clear_due_hint?: boolean } = {};
    if (trimmed !== subject.trim()) patch.subject = trimmed;
    if (draftDue !== originalDue) {
      if (draftDue === '') patch.clear_due_hint = true;
      // Midday UTC: a date-only input has no time, and midnight would slide to
      // the previous day for anyone west of Greenwich.
      else patch.due_hint = `${draftDue}T12:00:00Z`;
    }
    onSave(patch);
  };

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={event => {
        event.preventDefault();
        submit();
      }}
    >
      {/* The control lives INSIDE its label: `htmlFor` alone leaves
          jsx-a11y/control-has-associated-label unconvinced, and nesting is the
          form that needs no id to stay associated. */}
      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-medium text-muted-foreground">
          {t('settings.open_loops.edit_subject_label')}
        </span>
        <input
          type="text"
          // Visible label AND aria-label: the ratchet asks controls to carry
          // their own accessible name, and both read the same words so a
          // screen reader and a sighted user hear/see the same thing.
          aria-label={t('settings.open_loops.edit_subject_label')}
          value={draftSubject}
          onChange={event => setDraftSubject(event.target.value)}
          maxLength={500}
          autoFocus
          className="rounded-md border border-border/60 bg-background px-2 py-1 text-sm"
        />
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('settings.open_loops.edit_due_label')}
          </span>
          <input
            type="date"
            aria-label={t('settings.open_loops.edit_due_label')}
            value={draftDue}
            onChange={event => setDraftDue(event.target.value)}
            className="rounded-md border border-border/60 bg-background px-2 py-1 text-sm"
          />
        </label>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="submit"
            aria-disabled={blocked}
            aria-label={t('settings.open_loops.edit_save')}
            title={t('settings.open_loops.edit_save')}
            className={`rounded-md border border-border/40 p-1.5 ${
              blocked ? 'opacity-40' : 'hover:bg-background hover:text-primary'
            }`}
          >
            <Check className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button
            type="button"
            onClick={onCancel}
            aria-label={t('common.cancel')}
            title={t('common.cancel')}
            className="rounded-md border border-border/40 p-1.5 hover:bg-background"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </form>
  );
}

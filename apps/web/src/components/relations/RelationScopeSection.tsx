'use client';

/**
 * What a "360° point" is allowed to read — chosen here, applied by the tool.
 *
 * The request leaves this page as a chat `?intent=`, which carries prose and
 * nothing else. Letting the planner infer the scope from that sentence would
 * make this panel a suggestion; the selection is therefore SAVED server-side
 * and the tool reads it back. That is also why `prepare` awaits the write
 * before navigating: a fire-and-forget save races the tool that reads it, and
 * the reader would get their previous scope with no way to tell.
 *
 * Defaults are pre-filled from the stored value — "what I usually want" — and
 * every edit is a new default. One stored value serves both purposes.
 */

import { useCallback, useState } from 'react';
import { Sparkles, Target } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { CollapsibleSection } from '@/components/relations/CollapsibleSection';
import {
  OVERVIEW_DIRECTIONS,
  OVERVIEW_ROLES,
  OVERVIEW_SECTIONS,
  useOverviewScope,
} from '@/hooks/useRelations';
import type {
  OverviewDirection,
  OverviewRole,
  OverviewSection,
  RelationOverviewScope,
} from '@/hooks/useRelations';

/**
 * What the panel shows for the instant before the server answers.
 *
 * Mirrors the backend default (`RelationOverviewScope.default()`), and is only
 * ever visible during that first read: the GET always returns a resolved
 * scope, so this never becomes a second source of truth.
 */
const FALLBACK_SCOPE: RelationOverviewScope = {
  sections: [...OVERVIEW_SECTIONS],
  directions: [...OVERVIEW_DIRECTIONS],
  roles: [...OVERVIEW_ROLES],
  max_items: 5,
};

/**
 * The ceiling the backend enforces, mirrored so the field can STATE it.
 *
 * Source of truth: `RELATION_OVERVIEW_MAX_ITEMS_CEILING` in
 * `apps/api/src/core/constants.py` — grep that name to find both sides. A
 * limit the server applies without telling the form is a trap (ADR-184), and
 * the safe failure is designed in: if the two ever drift, the PUT answers 422,
 * `save` reports false, and the chat opens on the STORED scope rather than on
 * a value that never applied.
 */
const MAX_ITEMS_CEILING = 25;

/** Add or remove one value — the list IS the selection, order is irrelevant. */
function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter(other => other !== value) : [...list, value];
}

/**
 * The stored scope, the reader's pending edits, and the write that commits them.
 *
 * `draft ?? stored` derives during render rather than syncing in an effect: a
 * refetch that landed after an edit must never overwrite what the reader just
 * ticked.
 */
export function useScopeDraft() {
  const { scope: stored, saving, save } = useOverviewScope();
  const [draft, setDraft] = useState<RelationOverviewScope | null>(null);
  const scope = draft ?? stored ?? FALLBACK_SCOPE;

  const commit = useCallback(() => save(scope), [save, scope]);
  return { scope, setDraft, saving, commit };
}

/** One checkbox of the selector — 44 px tall, labelled, keyboard-native. */
function ScopeCheckbox({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-2 text-sm hover:bg-muted/40"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={onChange}
        // Same string as the visible text, from the same variable: the
        // wrapping `<label>` already names it for a browser, but the a11y
        // ratchet requires the name to be on the control itself so it cannot
        // be lost by a later refactor of the row.
        aria-label={label}
        className="h-4 w-4 shrink-0 accent-primary"
      />
      <span className="min-w-0">{label}</span>
    </label>
  );
}

/** One group of checkboxes, named by its legend for assistive technology. */
function ScopeGroup({ legend, children }: { legend: string; children: React.ReactNode }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {legend}
      </legend>
      {/* One column on a phone, two from `sm`: these labels are words, not
          values, so they wrap badly in a narrow grid. */}
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

export function RelationScopeSection({
  scope,
  saving,
  onChange,
  onPrepare,
}: {
  scope: RelationOverviewScope;
  saving: boolean;
  onChange: (scope: RelationOverviewScope) => void;
  onPrepare: () => void;
}) {
  const { t } = useTranslation();
  const nothingSelected = scope.sections.length === 0;

  const setSections = (section: OverviewSection) =>
    onChange({ ...scope, sections: toggle(scope.sections, section) });
  const setDirections = (direction: OverviewDirection) =>
    onChange({ ...scope, directions: toggle(scope.directions, direction) });
  const setRoles = (role: OverviewRole) => onChange({ ...scope, roles: toggle(scope.roles, role) });

  return (
    <CollapsibleSection icon={Target} title={t('relations.scope_title')}>
      <p className="text-xs text-muted-foreground">{t('relations.scope_hint')}</p>

      <ScopeGroup legend={t('relations.scope_sections_legend')}>
        {OVERVIEW_SECTIONS.map(section => (
          <ScopeCheckbox
            key={section}
            id={`scope-section-${section}`}
            label={t(`relations.section_${section}`)}
            checked={scope.sections.includes(section)}
            onChange={() => setSections(section)}
          />
        ))}
      </ScopeGroup>

      <ScopeGroup legend={t('relations.scope_directions_legend')}>
        {OVERVIEW_DIRECTIONS.map(direction => (
          <ScopeCheckbox
            key={direction}
            id={`scope-direction-${direction}`}
            label={t(`relations.peer_message_${direction}`)}
            checked={scope.directions.includes(direction)}
            onChange={() => setDirections(direction)}
          />
        ))}
      </ScopeGroup>

      <ScopeGroup legend={t('relations.scope_roles_legend')}>
        {OVERVIEW_ROLES.map(role => (
          <ScopeCheckbox
            key={role}
            id={`scope-role-${role}`}
            label={t(`relations.event_role_${role}`)}
            checked={scope.roles.includes(role)}
            onChange={() => setRoles(role)}
          />
        ))}
      </ScopeGroup>

      <label
        htmlFor="scope-max-items"
        className="flex min-h-11 flex-wrap items-center gap-2 text-sm"
      >
        <span>{t('relations.scope_max_items')}</span>
        <input
          id="scope-max-items"
          type="number"
          min={1}
          max={MAX_ITEMS_CEILING}
          aria-label={t('relations.scope_max_items')}
          value={scope.max_items}
          onChange={event =>
            onChange({
              ...scope,
              // An empty or non-numeric field must not become 0 — the server
              // would reject the whole write and the reader would lose every
              // box they just ticked.
              max_items: Number.isFinite(event.target.valueAsNumber)
                ? Math.min(Math.max(Math.round(event.target.valueAsNumber), 1), MAX_ITEMS_CEILING)
                : scope.max_items,
            })
          }
          // 16px on mobile: anything smaller makes iOS Safari zoom the page in
          // on focus and never zoom back out.
          className="w-20 rounded-md border border-border/60 bg-background px-2 py-1.5 text-base sm:text-sm"
        />
      </label>

      {nothingSelected && (
        <p className="text-xs text-amber-600 dark:text-amber-500">{t('relations.scope_empty')}</p>
      )}

      <button
        type="button"
        // The guard sits next to the attribute that announces it: split
        // across two components they drift, and a button that says "disabled"
        // while still firing is worse than either.
        onClick={() => {
          if (saving || nothingSelected) return;
          onPrepare();
        }}
        // `aria-disabled`, never `disabled`: a control disabled while focused
        // is blurred by the browser and leaves the tab order.
        aria-disabled={saving || nothingSelected}
        className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
      >
        <Sparkles className="h-4 w-4" aria-hidden="true" />
        {t('relations.scope_launch')}
      </button>
    </CollapsibleSection>
  );
}

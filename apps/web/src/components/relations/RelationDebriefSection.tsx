'use client';

/**
 * RelationDebriefSection — the answer the reader came for, at the top of the card.
 *
 * A relationship card stacks ten sections. Nobody reads ten sections. This one
 * is a written synthesis of the whole file: where you stand, what is open, what
 * to raise next — so it does NOT fold, and it sits above everything the reader
 * would otherwise have to assemble in their head.
 *
 * Three honesty rules it renders rather than hides:
 *
 * - **it always states WHEN it was written.** A synthesis without its date is a
 *   claim about now, and this one is rebuilt at most once a day;
 * - **it names what could not be read.** A section the account could not reach
 *   is a gap, not an absence — saying nothing would let the reader take a
 *   partial picture for a complete one;
 * - **a failed refresh leaves the previous debrief standing**, under a line
 *   saying the refresh failed. Replacing a usable text with an empty panel
 *   turns "I could not refresh this" into "there is nothing".
 *
 * Accessibility: a refresh announces itself with `aria-busy` and never unmounts
 * the subtree (a reader mid-sentence must not lose it), and the rebuild control
 * uses `aria-disabled` plus a guard in the handler rather than `disabled`,
 * which would blur it and drop it from the tab order.
 */

import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Sparkles } from 'lucide-react';

import { RefreshButton } from '@/components/relations/CollapsibleSection';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

import type { RelationDebrief } from '@/hooks/useRelations';

/** How a stored instant is shown — the reader's locale, never a raw ISO string. */
function formatWritten(value: string | null, lng: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString(lng, { dateStyle: 'medium', timeStyle: 'short' });
}

/**
 * The card shell — one border, one padding, shared by every state below.
 *
 * The header carries the title and, at most, the ONE refresh affordance the
 * whole card uses. The switch is a SETTING, not an action: it sits at the foot,
 * out of the path the reader scans (ADR-208's rule for metadata one consults
 * rather than scans). Three labelled controls in a section header is a toolbar,
 * and this section is a paragraph.
 */
function Shell({
  children,
  busy,
  action,
  foot,
}: {
  children: React.ReactNode;
  busy?: boolean;
  action?: React.ReactNode;
  foot: React.ReactNode;
}) {
  const { t } = useTranslation();
  // `useId`, never a literal: an id written by hand collides the moment two of
  // these render, and `aria-labelledby` then points at the wrong heading.
  const titleId = useId();
  return (
    <section
      aria-busy={busy || undefined}
      aria-labelledby={titleId}
      className="rounded-xl border border-border/50 bg-card p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h3
          id={titleId}
          className="flex min-w-0 items-center gap-2 text-sm font-semibold text-foreground"
        >
          <Sparkles className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="truncate">{t('relations.debrief_title')}</span>
        </h3>
        {action}
      </div>
      <div className="mt-3">{children}</div>
      {foot}
    </section>
  );
}

/**
 * The switch that turns the whole capability off, wherever the reader sees it.
 *
 * Its own `<button role="switch">` rather than the shared `Switch`: that
 * primitive draws its track ON the button, whose box is 36 x 20 CSS px, and a
 * touch target under 44 px is a control a thumb misses (WCAG 2.5.5, measured by
 * the relations phone-screen journey). The label is INSIDE the control, so the
 * whole row is the target and the words are tappable — a wrapping `<label>`
 * would have grown the measured box without making anything clickable, since a
 * button is not a labelable element.
 */
function DebriefSwitch({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (next: boolean) => void;
}) {
  const { t } = useTranslation();
  const labelId = useId();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-labelledby={labelId}
      onClick={() => onChange(!enabled)}
      className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-md px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span id={labelId} className="text-xs text-muted-foreground">
        {t('relations.debrief_switch')}
      </span>
      {/* Decorative: the button above carries the role, the state and the name. */}
      <span
        aria-hidden="true"
        className={cn(
          'inline-flex h-5 w-9 shrink-0 items-center rounded-full border-2 border-transparent shadow-sm transition-colors',
          enabled ? 'bg-primary' : 'bg-input'
        )}
      >
        <span
          className={cn(
            'block h-4 w-4 rounded-full bg-background shadow-lg transition-transform',
            enabled ? 'translate-x-4' : 'translate-x-0'
          )}
        />
      </span>
    </button>
  );
}

/** Which sentence a bodyless card shows — one table, never a nested ternary. */
const NOTICE_KEY: Record<string, string> = {
  empty: 'relations.debrief_empty',
  true: 'relations.debrief_failed',
  false: 'relations.debrief_absent',
};

/** One titled block of the synthesis — the meeting-report shape, reused. */
function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      <div className="mt-1">{children}</div>
    </div>
  );
}

/** A list of points, drawn the way every other LLM-written report here is. */
function Bullets({ items, muted }: { items: string[]; muted?: boolean }) {
  return (
    <ul
      className={
        muted
          ? 'list-disc space-y-1 pl-5 text-sm text-muted-foreground'
          : 'list-disc space-y-1 pl-5 text-sm'
      }
    >
      {items.map(item => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

/** The written synthesis, field by field — an empty field renders nothing. */
function DebriefBody({ debrief }: { debrief: RelationDebrief }) {
  const { t } = useTranslation();
  const body = debrief.body;
  if (!body) return null;
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium leading-relaxed text-foreground">{body.headline}</p>
      <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
        {body.where_we_stand}
      </p>
      {body.open_points.length > 0 && (
        <Block title={t('relations.debrief_open_points')}>
          <Bullets items={body.open_points} />
        </Block>
      )}
      {body.suggested_next_step && (
        <Block title={t('relations.debrief_next_step')}>
          <p className="text-sm">{body.suggested_next_step}</p>
        </Block>
      )}
      {body.notable_facts.length > 0 && (
        <Block title={t('relations.debrief_notable_facts')}>
          <Bullets items={body.notable_facts} muted />
        </Block>
      )}
    </div>
  );
}

/**
 * The foot of the card: where the debrief comes from, and the switch that
 * turns it off.
 *
 * Both are stated because both change how the block above should be read — a
 * synthesis whose provenance is invisible reads as a fact about right now — and
 * the switch lives HERE rather than in the header because it is a setting the
 * reader consults, not an action they scan for (ADR-208).
 */
function DebriefFoot({
  debrief,
  lng,
  enabled,
  onToggle,
}: {
  debrief: RelationDebrief | null;
  lng: string;
  enabled: boolean;
  onToggle: (next: boolean) => void;
}) {
  const { t } = useTranslation();
  const written = debrief ? formatWritten(debrief.generated_at, lng) : null;
  const gaps = debrief?.unavailable.length ?? 0;
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t border-border/40 pt-2">
      <p className="flex min-w-0 flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
        <span>
          {written && t('relations.debrief_written_at', { when: written })}
          {gaps > 0 && (
            <>
              {written && ' — '}
              {t('relations.debrief_unavailable', { count: gaps })}
            </>
          )}
        </span>
        {debrief?.usage && <LLMUsageBadge usage={debrief.usage} />}
      </p>
      <DebriefSwitch enabled={enabled} onChange={onToggle} />
    </div>
  );
}

/**
 * What the card should show, decided once, away from any JSX.
 *
 * The five states cascade — off, first read, a build over nothing, an answer,
 * an answer that could not be refreshed — and expressing that cascade inside
 * the render turned one function into a complexity hotspot the audit gate
 * refuses. As a pure decision it is also directly testable, which is what the
 * two states nobody sees in a screenshot actually need.
 */
export type DebriefView =
  | { kind: 'disabled' }
  | { kind: 'skeleton' }
  | { kind: 'building' }
  | { kind: 'empty' }
  | { kind: 'notice'; failed: boolean }
  | { kind: 'body'; refreshFailed: boolean };

export function resolveDebriefView({
  debrief,
  loading,
  building,
  enabled,
}: {
  debrief: RelationDebrief | null;
  loading: boolean;
  building: boolean;
  enabled: boolean;
}): DebriefView {
  // Off is a decision, not an error: the capability collapses to the one row
  // that turns it back on. A feature that vanishes with no way back is a bug.
  if (!enabled) return { kind: 'disabled' };
  if (loading) return { kind: 'skeleton' };

  const status = debrief?.status ?? 'absent';
  const hasBody = !!debrief?.body;
  // A build in flight over nothing yet: announce it, never a spinner that
  // replaces content the reader may already be looking at.
  if (building && !hasBody) return { kind: 'building' };
  if (hasBody) return { kind: 'body', refreshFailed: status === 'failed' };
  if (status === 'empty') return { kind: 'empty' };
  return { kind: 'notice', failed: status === 'failed' };
}

export function RelationDebriefSection({
  debrief,
  loading,
  building,
  enabled,
  lng,
  onRebuild,
  onToggle,
}: {
  debrief: RelationDebrief | null;
  /** First read only — a refresh never stages a skeleton. */
  loading: boolean;
  building: boolean;
  enabled: boolean;
  lng: string;
  onRebuild: () => void;
  onToggle: (next: boolean) => void;
}) {
  const { t } = useTranslation();
  const view = resolveDebriefView({ debrief, loading, building, enabled });
  // The switch travels with every state, including the one where the feature is
  // off: a capability that vanishes with no way back is a defect, not a saving.
  const foot = (
    <DebriefFoot
      debrief={view.kind === 'body' ? debrief : null}
      lng={lng}
      enabled={enabled}
      onToggle={onToggle}
    />
  );

  if (view.kind === 'disabled') {
    return (
      <Shell foot={foot}>
        <p className="text-sm text-muted-foreground">{t('relations.debrief_disabled')}</p>
      </Shell>
    );
  }

  if (view.kind === 'skeleton') {
    return (
      <Shell busy foot={foot}>
        <div className="space-y-2" aria-hidden="true">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </Shell>
    );
  }

  const canRebuild = !building && (debrief?.can_rebuild ?? true);
  const action = (
    <RefreshButton
      label={t('relations.debrief_rebuild')}
      busy={!canRebuild}
      onRefresh={onRebuild}
    />
  );

  if (view.kind === 'building') {
    return (
      <Shell busy action={action} foot={foot}>
        <p className="text-sm text-muted-foreground">{t('relations.debrief_building')}</p>
      </Shell>
    );
  }

  if (view.kind !== 'body') {
    return (
      <Shell busy={building} action={action} foot={foot}>
        <EmptyState
          icon={view.kind === 'notice' && view.failed ? AlertTriangle : Sparkles}
          description={t(NOTICE_KEY[view.kind === 'empty' ? 'empty' : String(view.failed)])}
          reason="no-data"
        />
      </Shell>
    );
  }

  return (
    <Shell busy={building} action={action} foot={foot}>
      {view.refreshFailed && (
        <p className="mb-3 flex items-start gap-2 rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {t('relations.debrief_refresh_failed')}
        </p>
      )}
      <DebriefBody debrief={debrief!} />
    </Shell>
  );
}

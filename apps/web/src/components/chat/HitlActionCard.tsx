'use client';

/**
 * HitlActionCard — one-click approval card (Lot 1 P1-V1).
 *
 * Renders the pending HITL interrupt as an actionable card above the chat
 * input: backend-driven buttons (wire action ids pass through verbatim — the
 * server canonicalizes aliases), per-kind content preview, and the full
 * lifecycle (awaiting → submitting → resolved / expired). The card is a
 * progressive enhancement: the typed/voice reply channel stays fully
 * functional next to it, and answering by text resolves the card via_text.
 *
 * Kinds rendered: tool_confirmation, draft_critique, destructive_confirm,
 * for_each_confirmation (the normalizer returns null for anything else).
 */

import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  CircleSlash,
  Clock,
  ListChecks,
  Mail,
  Wrench,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { HitlActionOption, HitlCardState, NormalizedHitlPayload } from '@/types/hitl';

export interface HitlActionCardProps {
  hitl: HitlCardState;
  /**
   * Button press: receives the VERBATIM wire action id and the translated
   * label (sent as the user-visible message content). For the draft inline
   * edit (P1-V2) the third argument carries the modification instructions —
   * they double as the visible message, mirroring the natural-language path.
   */
  onAction: (wireAction: string, labelText: string, modificationInstructions?: string) => void;
}

const KIND_ICONS = {
  tool_confirmation: Wrench,
  draft_critique: Mail,
  destructive_confirm: AlertTriangle,
  for_each_confirmation: ListChecks,
} as const;

const BUTTON_VARIANTS: Record<
  HitlActionOption['style'],
  'default' | 'outline' | 'destructive' | 'ghost'
> = {
  primary: 'default',
  secondary: 'outline',
  destructive: 'destructive',
  ghost: 'ghost',
};

/** Compact key/value preview of tool arguments (strings/numbers only). */
function ToolArgsPreview({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args)
    .filter(([, v]) => typeof v === 'string' || typeof v === 'number')
    .slice(0, 4);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-2 space-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2 text-xs">
          <dt className="shrink-0 font-medium text-muted-foreground">{key}</dt>
          <dd className="truncate text-foreground">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Typed preview of a draft (email fields first, generic fallback). */
function DraftPreview({ payload }: { payload: NormalizedHitlPayload }) {
  const { t } = useTranslation();
  const content = payload.draftContent ?? {};
  const to = typeof content.to === 'string' ? content.to : null;
  const subject = typeof content.subject === 'string' ? content.subject : null;
  const body = typeof content.body === 'string' ? content.body : null;

  return (
    <div className="mt-2 space-y-1 text-xs">
      {to && (
        <div className="flex gap-2">
          <span className="shrink-0 font-medium text-muted-foreground">
            {t('chat.hitl.draft.to')}
          </span>
          <span className="truncate">{to}</span>
        </div>
      )}
      {subject && (
        <div className="flex gap-2">
          <span className="shrink-0 font-medium text-muted-foreground">
            {t('chat.hitl.draft.subject')}
          </span>
          <span className="truncate">{subject}</span>
        </div>
      )}
      {body && <p className="line-clamp-3 whitespace-pre-line text-muted-foreground">{body}</p>}
    </div>
  );
}

function ResolutionBadge({ hitl }: { hitl: HitlCardState }) {
  const { t } = useTranslation();
  if (hitl.status === 'expired') {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
        {t('chat.hitl.expired')}
      </p>
    );
  }
  if (hitl.status !== 'resolved') return null;
  const resolution = hitl.resolution ?? 'via_text';
  const Icon = resolution === 'confirmed' ? Check : resolution === 'cancelled' ? X : CircleSlash;
  return (
    <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {t(`chat.hitl.resolved.${resolution}`)}
    </p>
  );
}

/** Severity → container/icon tone classes (single lookup, no ternary chains). */
const TONES = {
  critical: {
    section: 'border-destructive/40 bg-destructive/5',
    icon: 'bg-destructive/15 text-destructive',
  },
  warning: { section: 'border-warning/40 bg-warning/5', icon: 'bg-warning/15 text-warning' },
  default: { section: 'border-primary/30 bg-card/70', icon: 'bg-primary/15 text-primary' },
} as const;

function toneFor(severity: NormalizedHitlPayload['severity']) {
  if (severity === 'critical') return TONES.critical;
  if (severity === 'warning') return TONES.warning;
  return TONES.default;
}

/** Per-kind content body (tool identity / draft fields / scale line). */
function CardBody({ payload }: { payload: NormalizedHitlPayload }) {
  const { t } = useTranslation();

  if (payload.kind === 'tool_confirmation') {
    return (
      <>
        {payload.toolName && (
          <p className="mt-1 truncate text-xs text-muted-foreground">{payload.toolName}</p>
        )}
        {payload.toolArgs && <ToolArgsPreview args={payload.toolArgs} />}
      </>
    );
  }
  if (payload.kind === 'draft_critique') {
    return <DraftPreview payload={payload} />;
  }
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      {typeof payload.affectedCount === 'number' &&
        t('chat.hitl.affected_count', { count: payload.affectedCount })}
      {payload.operationType && <span className="ml-1 font-medium">{payload.operationType}</span>}
    </p>
  );
}

function ActionButtons({
  payload,
  submitting,
  onAction,
  onEditToggle,
}: {
  payload: NormalizedHitlPayload;
  submitting: boolean;
  onAction: HitlActionCardProps['onAction'];
  /** Present when the card supports inline edit — 'edit' toggles the form. */
  onEditToggle?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      {payload.actions.map(option => {
        const label = t(`chat.hitl.actions.${option.label}`);
        const isEditToggle = option.action === 'edit' && onEditToggle;
        return (
          <Button
            key={option.action}
            type="button"
            size="sm"
            variant={BUTTON_VARIANTS[option.style]}
            disabled={submitting}
            onClick={() => (isEditToggle ? onEditToggle() : onAction(option.action, label))}
          >
            {label}
          </Button>
        );
      })}
    </>
  );
}

/**
 * Inline draft edit form (P1-V2): free-text modification instructions routed
 * as a structured 'edit' decision (classifier bypassed). Escape returns to
 * the buttons; submit requires non-blank instructions.
 */
function DraftEditForm({
  submitting,
  onSubmit,
  onCancel,
}: {
  submitting: boolean;
  onSubmit: (instructions: string) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [instructions, setInstructions] = useState('');
  const trimmed = instructions.trim();

  return (
    <div className="mt-1 w-full space-y-2">
      <textarea
        autoFocus
        rows={2}
        value={instructions}
        onChange={e => setInstructions(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Escape') onCancel();
        }}
        placeholder={t('chat.hitl.edit.placeholder')}
        aria-label={t('chat.hitl.edit.placeholder')}
        disabled={submitting}
        className="w-full resize-none rounded-md border border-border/60 bg-background/80 px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
      />
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={submitting || !trimmed}
          onClick={() => onSubmit(trimmed)}
        >
          {t('chat.hitl.edit.submit')}
        </Button>
        <Button type="button" size="sm" variant="ghost" disabled={submitting} onClick={onCancel}>
          {t('chat.hitl.edit.cancel')}
        </Button>
      </div>
    </div>
  );
}

export function HitlActionCard({ hitl, onAction }: HitlActionCardProps) {
  const { t } = useTranslation();
  // Edit mode keyed by the card's message id: a re-presented draft (new
  // interrupt, last-wins) automatically leaves edit mode — derived state,
  // no effect needed.
  const [editingForMessageId, setEditingForMessageId] = useState<string | null>(null);
  const { status, payload } = hitl;

  if (status === 'none' || !payload) return null;

  const Icon = KIND_ICONS[payload.kind];
  const tone = toneFor(payload.severity);
  const showButtons = status === 'awaiting' || status === 'submitting';
  const canEdit =
    payload.kind === 'draft_critique' && payload.actions.some(a => a.action === 'edit');
  const editing = editingForMessageId !== null && editingForMessageId === payload.messageId;
  const showEditForm = showButtons && editing && canEdit;
  const setEditing = (on: boolean) => setEditingForMessageId(on ? payload.messageId : null);

  return (
    <section
      aria-label={t(`chat.hitl.title.${payload.kind}`)}
      className={cn(
        'mx-auto mb-3 w-full max-w-4xl rounded-xl border px-4 py-3 shadow-sm backdrop-blur-sm',
        tone.section
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', tone.icon)}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground">
            {t(`chat.hitl.title.${payload.kind}`)}
          </p>

          <CardBody payload={payload} />

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {showButtons && !showEditForm && (
              <ActionButtons
                payload={payload}
                submitting={status === 'submitting'}
                onAction={onAction}
                onEditToggle={canEdit ? () => setEditing(true) : undefined}
              />
            )}
            {showEditForm && (
              <DraftEditForm
                submitting={status === 'submitting'}
                onSubmit={instructions => {
                  setEditing(false);
                  // The instructions double as the visible user message —
                  // parity with the natural-language critique path.
                  onAction('edit', instructions, instructions);
                }}
                onCancel={() => setEditing(false)}
              />
            )}
            <ResolutionBadge hitl={hitl} />
          </div>
        </div>
      </div>
    </section>
  );
}

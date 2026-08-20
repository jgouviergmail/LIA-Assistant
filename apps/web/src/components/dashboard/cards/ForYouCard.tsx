'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';
import { Check, CircleSlash, Pencil, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BriefingCard } from '../BriefingCard';
import type { CardItemAction } from './CardItemActions';
import { CardItemRow } from './CardItemRow';
import { CommitmentEditor } from '@/components/commitments/CommitmentEditor';
import { haptic } from '@/lib/haptics';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useOpenLoops, type OpenLoopPatch } from '@/hooks/useOpenLoops';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { Language } from '@/i18n/settings';
import type { CardSection, ForYouData } from '@/types/briefing';

interface ForYouCardProps {
  section: CardSection<ForYouData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/**
 * « For you » card (P15, interdomain program Lot 4).
 *
 * Aggregates the commitments ledger (open loops, ADR-139) and the
 * automations digest (ADR-140). Only the UPCOMING execution is shown — past
 * runs are deliberately not displayed (owner arbitration 2026-07-30); the
 * API payload still carries them unchanged. Loop rows deep-link to the chat
 * prefilled with a direction-aware intent (QW-9 `?draft=` mechanism) —
 * nothing is auto-sent.
 */
export function ForYouCard({ section, isRefreshing, onRefresh, staggerIndex }: ForYouCardProps) {
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<ForYouData>
      titleKey="dashboard.briefing.cards.for_you.title"
      icon={<Sparkles className="h-5 w-5" />}
      tone="fuchsia"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.for_you.empty"
      renderContent={data => (
        <ForYouContent
          data={data}
          onOpenChat={draft => openChatDeepLink(chatDraftHref(lng, draft))}
          onChanged={onRefresh}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function ForYouContent({
  data,
  onOpenChat,
  onChanged,
}: {
  data: ForYouData;
  onOpenChat: (draft: string) => void;
  /** Reload the section from the server rather than guessing the new list. */
  onChanged: () => void;
}) {
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  const listRef = useRef<HTMLUListElement>(null);
  const [editing, setEditing] = useState<ForYouData['open_loops'][number] | null>(null);
  const [saving, setSaving] = useState(false);
  // Ids with a close in flight. The row STAYS on screen until the reload
  // lands — unlike the ledger, whose optimistic removal takes it away — so a
  // second click is reachable, and it would hit a commitment the API just
  // closed (`404 Open_loop not found`).
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  // The LEDGER's hook, not a second implementation: the dashboard and the
  // settings ledger must drive the same writes, or the two surfaces disagree
  // about what is still open. `enabled: false` — this card renders the
  // BRIEFING section and needs only the mutations, never a second list.
  const { close, update } = useOpenLoops(false);
  const { config } = useAppConfig();

  /** Take focus back into the card BEFORE the row disappears. */
  const anchorFocus = () => {
    listRef.current?.closest<HTMLElement>('[role="region"]')?.focus();
  };

  const closeLoop = async (id: string, action: 'done' | 'dismissed') => {
    // The GUARD, not the attribute, is what prevents the double submit.
    if (pending.has(id)) return;
    setPending(prev => new Set(prev).add(id));
    let ok = false;
    try {
      ok = await close(id, action);
    } finally {
      setPending(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
    // Focus first, while the row still exists — then ask for the reload that
    // removes it.
    anchorFocus();
    if (!ok) {
      // Never silent: the row stays either way, so saying nothing would read
      // as "it worked" — the worse of the two readings.
      toast.error(t('common.error'));
      return;
    }
    haptic('confirm');
    // The card renders the BRIEFING section, not this hook's own list: the
    // hook's optimistic removal is invisible here. Without this reload the
    // closed commitment stays on screen and the next click lands on a row the
    // API has already closed — `404 Open_loop not found`.
    onChanged();
  };

  const saveEdit = async (patch: OpenLoopPatch) => {
    if (!editing) return;
    setSaving(true);
    let ok = false;
    try {
      ok = await update(editing.id, patch);
    } finally {
      setSaving(false);
      setEditing(null);
      anchorFocus();
    }
    // Same reason as above: without a reload the card keeps showing the OLD
    // subject until the section's own cache expires.
    if (ok) onChanged();
  };

  return (
    <div className="space-y-3">
      {data.open_loops.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            {/* UXR Lot 7 (B5): the heading opens the full open-loops ledger.
                (N-09 CRM has its own entry in Quick Access — the ledger link
                stays as the signed-off B5 behavior.)

                The TYPED target, not the settings root: `open-loops` is a
                declared token, so the page activates its tab, expands its
                accordion item and scrolls it clear of the sticky chrome. A
                bare `/dashboard/settings` landed the reader at the top of ~30
                collapsed sections with nothing opened. The link is only
                rendered when loops exist, and the fetcher only fills them
                under `open_loops_enabled` — the same flag that decides whether
                the section renders at all, so this can never point at an
                absent target. */}
            <Link
              href={settingsSectionHref(lng, 'open-loops')}
              className="hover:text-primary hover:underline"
            >
              {t('dashboard.briefing.cards.for_you.loops_title')}
            </Link>
          </p>
          <ul ref={listRef} className="space-y-0.5" role="list">
            {data.open_loops.map(loop => {
              const intent = t(
                loop.direction === 'waiting_on_other'
                  ? 'dashboard.briefing.intents.loop_waiting'
                  : 'dashboard.briefing.intents.loop_owed',
                { subject: loop.subject }
              );
              // The ledger's three, where the reader already is. Sending them
              // to settings would mean finding this same row a second time on
              // another page. One tap, no dialog — the ledger is documented as
              // "one-tap actions", and closing a commitment is not a deletion.
              const actions: CardItemAction[] = [
                {
                  icon: Check,
                  label: t('dashboard.briefing.actions.loop_done'),
                  onSelect: () => void closeLoop(loop.id, 'done'),
                  busy: pending.has(loop.id),
                },
                {
                  icon: CircleSlash,
                  label: t('dashboard.briefing.actions.loop_dismiss'),
                  onSelect: () => void closeLoop(loop.id, 'dismissed'),
                  busy: pending.has(loop.id),
                },
                {
                  icon: Pencil,
                  label: t('dashboard.briefing.actions.loop_edit'),
                  onSelect: () => setEditing(loop),
                },
              ];
              return (
                <CardItemRow
                  key={loop.id}
                  ariaLabel={intent}
                  tooltip={loop.subject}
                  onSelect={() => onOpenChat(intent)}
                  contentClassName="flex items-baseline justify-between gap-2 text-sm"
                  actions={actions}
                >
                  <span className="text-foreground/90 truncate font-medium">{loop.subject}</span>
                  <span className="shrink-0 text-xs text-fuchsia-600 dark:text-fuchsia-300 tabular-nums">
                    {t('dashboard.briefing.cards.for_you.days_open', {
                      count: loop.days_open,
                    })}
                  </span>
                </CardItemRow>
              );
            })}
          </ul>
        </div>
      )}
      {editing && (
        // The ledger's editor, reused: a correction starts from what is wrong,
        // and a second form would eventually disagree with the first about
        // what a commitment is allowed to be.
        <CommitmentEditor
          lng={lng as Language}
          subject={editing.subject}
          dueHint={editing.due_hint ?? null}
          saving={saving}
          onCancel={() => {
            setEditing(null);
            anchorFocus();
          }}
          onSave={patch => void saveEdit(patch)}
        />
      )}
      {data.next_automation && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            {t('dashboard.briefing.cards.for_you.automations_title')}
          </p>
          <ul className="space-y-0.5 text-sm" role="list">
            <li className="flex items-baseline justify-between gap-2">
              <span className="text-foreground/90 truncate">{data.next_automation.title}</span>
              <span className="shrink-0 text-xs font-semibold text-fuchsia-600 dark:text-fuchsia-300 tabular-nums">
                {/* Precise backend-formatted execution time; label fallback
                    keeps older cached payloads rendering. */}
                {data.next_automation.next_trigger_local ??
                  t('dashboard.briefing.cards.for_you.next_up')}
              </span>
            </li>
          </ul>
        </div>
      )}
      {/* Door to the full activity timeline (Lot 1-A1): this card previews
          what LIA tracks; the timeline is where ALL of its proactive work
          becomes visible. Gate-keeper rule (ADR-061): hidden when the
          instance disables the subsystem. */}
      {config?.features?.activity_timeline_enabled && (
        <p className="text-xs">
          <Link
            href={`/${lng}/dashboard/activity`}
            className="text-muted-foreground hover:text-primary hover:underline"
          >
            {t('activity.see_all')}
          </Link>
        </p>
      )}
    </div>
  );
}

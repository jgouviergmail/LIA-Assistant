'use client';

/**
 * OpenLoopsSection — consult/close view of the commitments ledger
 * (UXR Lot 7, B5; ADR-139). Settings surface (arbitration 4a), grouped by
 * direction, one-tap actions:
 *
 * - Fait → POST close {action: done} (closed_reason=api);
 * - Relancer → chat prefilled with the existing direction-aware intent
 *   (QW-9 `?draft=` — never auto-sent);
 * - Plus d'actualité → POST close {action: dismissed};
 * - Modifier → PATCH the subject/deadline the extractor got wrong
 *   (2026-08-02) — correcting is not creating, so the ledger stays
 *   automatic while ceasing to be wrong.
 *
 * No source column (arbitration 5a — single-conversation model) and no
 * manual creation (the ledger's value is being automatic). Renders nothing
 * when the instance flag is off or the surface is unavailable.
 */

import { Check, CircleSlash, ListTodo, Pencil, Send } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { CommitmentEditor } from '@/components/commitments/CommitmentEditor';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAppConfig } from '@/hooks/useAppConfig';
import {
  daysOpen,
  groupLoops,
  useOpenLoops,
  type OpenLoop,
  type OpenLoopPatch,
} from '@/hooks/useOpenLoops';
import { useTranslation } from '@/i18n/client';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { Language } from '@/i18n/settings';
import type { BaseSettingsProps } from '@/types/settings';

export function OpenLoopsSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const flagOn = !!config?.features?.open_loops_enabled;
  const { loops, unavailable, loadError, refetch, close, update } = useOpenLoops(flagOn);

  if (!flagOn || unavailable) return null;

  const groups = groupLoops(loops);

  const content = (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('settings.open_loops.description')}</p>
      {loadError ? (
        // Transient failure (network, 5xx) — same retry affordance as the
        // sibling settings sections, never a silently vanished feature.
        <div className="flex items-center gap-3">
          <p className="text-sm text-muted-foreground">{t('common.error')}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm text-primary hover:underline"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : loops.length === 0 ? (
        <p className="text-sm italic text-muted-foreground">{t('settings.open_loops.empty')}</p>
      ) : (
        <>
          <LoopGroup
            titleKey="settings.open_loops.owed_title"
            loops={groups.owed}
            lng={lng}
            close={close}
            update={update}
          />
          <LoopGroup
            titleKey="settings.open_loops.waiting_title"
            loops={groups.waiting}
            lng={lng}
            close={close}
            update={update}
          />
        </>
      )}
    </div>
  );

  if (!collapsible) return content;

  return (
    <SettingsSection
      value="open-loops"
      title={t('settings.open_loops.title')}
      description={t('settings.open_loops.description')}
      icon={ListTodo}
    >
      {content}
    </SettingsSection>
  );
}

function LoopGroup({
  titleKey,
  loops,
  lng,
  close,
  update,
}: {
  titleKey: string;
  loops: OpenLoop[];
  lng: Language;
  close: (id: string, action: 'done' | 'dismissed') => Promise<boolean>;
  update: (id: string, patch: OpenLoopPatch) => Promise<boolean>;
}) {
  const { t, i18n } = useTranslation(lng);
  // Hooks BEFORE any early return: a group that empties would otherwise change
  // the hook order between renders (react-hooks/rules-of-hooks).
  // One row at a time: two open editors would compete for the same list.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const handleClose = async (loop: OpenLoop, action: 'done' | 'dismissed') => {
    const ok = await close(loop.id, action);
    if (!ok) toast.error(t('common.error'));
  };

  if (loops.length === 0) return null;

  const handleSave = async (loop: OpenLoop, patch: OpenLoopPatch) => {
    setSavingId(loop.id);
    const ok = await update(loop.id, patch);
    setSavingId(null);
    if (!ok) {
      toast.error(t('common.error'));
      return;
    }
    setEditingId(null);
    toast.success(t('settings.open_loops.edit_saved'));
  };

  const relaunch = (loop: OpenLoop) => {
    const intent = t(
      loop.direction === 'waiting_on_other'
        ? 'dashboard.briefing.intents.loop_waiting'
        : 'dashboard.briefing.intents.loop_owed',
      { subject: loop.subject }
    );
    openChatDeepLink(chatDraftHref(lng, intent));
  };

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        {t(titleKey)}
      </p>
      <ul className="space-y-1" role="list">
        {loops.map(loop => (
          <li
            key={loop.id}
            className="flex items-center gap-2 rounded-lg border border-border/40 bg-card/60 px-3 py-2"
          >
            {editingId === loop.id ? (
              <div className="min-w-0 flex-1">
                <CommitmentEditor
                  lng={lng}
                  subject={loop.subject}
                  dueHint={loop.due_hint ?? null}
                  saving={savingId === loop.id}
                  onCancel={() => setEditingId(null)}
                  onSave={patch => void handleSave(loop, patch)}
                />
              </div>
            ) : (
              <>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={loop.subject}>
                    {loop.subject}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {loop.counterparty ? `${loop.counterparty} · ` : ''}
                    {loop.due_hint
                      ? new Intl.DateTimeFormat(i18n.language, {
                          day: '2-digit',
                          month: 'short',
                        }).format(new Date(loop.due_hint)) + ' · '
                      : ''}
                    {t('dashboard.briefing.cards.for_you.days_open', {
                      count: daysOpen(loop.created_at, new Date()),
                    })}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingId(loop.id)}
                  aria-label={t('settings.open_loops.edit', { subject: loop.subject })}
                  title={t('settings.open_loops.edit_label')}
                  className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background hover:text-primary"
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => void handleClose(loop, 'done')}
                  aria-label={t('settings.open_loops.done', { subject: loop.subject })}
                  title={t('settings.open_loops.done_label')}
                  className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background hover:text-green-600"
                >
                  <Check className="h-3.5 w-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => relaunch(loop)}
                  aria-label={t('settings.open_loops.relaunch', { subject: loop.subject })}
                  title={t('settings.open_loops.relaunch_label')}
                  className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background hover:text-primary"
                >
                  <Send className="h-3.5 w-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => void handleClose(loop, 'dismissed')}
                  aria-label={t('settings.open_loops.dismiss', { subject: loop.subject })}
                  title={t('settings.open_loops.dismiss_label')}
                  className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background hover:text-orange-600"
                >
                  <CircleSlash className="h-3.5 w-3.5" aria-hidden />
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

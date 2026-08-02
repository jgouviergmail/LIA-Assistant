'use client';

/**
 * OpenLoopsSection — consult/close view of the commitments ledger
 * (UXR Lot 7, B5; ADR-139). Settings surface (arbitration 4a), grouped by
 * direction, one-tap actions:
 *
 * - Fait → POST close {action: done} (closed_reason=api);
 * - Relancer → chat prefilled with the existing direction-aware intent
 *   (QW-9 `?draft=` — never auto-sent);
 * - Plus d'actualité → POST close {action: dismissed}.
 *
 * No source column (arbitration 5a — single-conversation model) and no
 * manual creation (the ledger's value is being automatic). Renders nothing
 * when the instance flag is off or the surface is unavailable.
 */

import { Check, CircleSlash, ListTodo, Send } from 'lucide-react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAppConfig } from '@/hooks/useAppConfig';
import { daysOpen, groupLoops, useOpenLoops, type OpenLoop } from '@/hooks/useOpenLoops';
import { useTranslation } from '@/i18n/client';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { Language } from '@/i18n/settings';
import type { BaseSettingsProps } from '@/types/settings';

export function OpenLoopsSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const flagOn = !!config?.features?.open_loops_enabled;
  const { loops, unavailable, loadError, refetch, close } = useOpenLoops(flagOn);

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
          />
          <LoopGroup
            titleKey="settings.open_loops.waiting_title"
            loops={groups.waiting}
            lng={lng}
            close={close}
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
}: {
  titleKey: string;
  loops: OpenLoop[];
  lng: Language;
  close: (id: string, action: 'done' | 'dismissed') => Promise<boolean>;
}) {
  const { t, i18n } = useTranslation(lng);
  if (loops.length === 0) return null;

  const handleClose = async (loop: OpenLoop, action: 'done' | 'dismissed') => {
    const ok = await close(loop.id, action);
    if (!ok) toast.error(t('common.error'));
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
          </li>
        ))}
      </ul>
    </div>
  );
}

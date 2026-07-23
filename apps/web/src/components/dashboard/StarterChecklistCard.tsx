'use client';

/**
 * StarterChecklistCard — "getting started" progression card on the dashboard
 * (UXR Lot 6, A10). Exposes the instance's dormant capabilities: each item's
 * state is DETECTED live through the existing hooks (never stored); only the
 * dismissal/celebration is server-persisted (`users.onboarding_checklist`).
 *
 * Rules (program doc): items gated on instance flags (ADR-061 gate-keeper —
 * a disabled subsystem is never offered); once `dismissed_at` OR
 * `celebrated_at` is set the card NEVER renders again; a user already at
 * 100% on first sight gets `celebrated_at` stamped silently (no retroactive
 * fanfare); a live transition to 100% shows a single discreet line, then
 * persists. A failed probe counts as not-done — never a crash.
 */

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { CheckCircle2, Circle, ListChecks, PartyPopper, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useChannelBindings } from '@/hooks/useChannelBindings';
import { useHeartbeatSettings } from '@/hooks/useHeartbeatSettings';
import { usePersonality } from '@/hooks/usePersonality';
import { useScheduledActions } from '@/hooks/useScheduledActions';
import { useSpaces } from '@/hooks/useSpaces';

export type ChecklistItemId =
  | 'connector'
  | 'personality'
  | 'voice'
  | 'telegram'
  | 'heartbeat'
  | 'space'
  | 'automation';

export interface ChecklistFlags {
  channels: boolean;
  heartbeat: boolean;
  ragSpaces: boolean;
}

/** Items offered on THIS instance (gate-keeper: disabled subsystems absent). */
export function visibleChecklistItems(flags: ChecklistFlags): ChecklistItemId[] {
  const items: ChecklistItemId[] = ['connector', 'personality', 'voice'];
  if (flags.channels) items.push('telegram');
  if (flags.heartbeat) items.push('heartbeat');
  if (flags.ragSpaces) items.push('space');
  items.push('automation');
  return items;
}

export interface ChecklistState {
  dismissed_at?: string;
  celebrated_at?: string;
}

/** Once dismissed or celebrated, the card never renders again. */
export function shouldRenderChecklist(state: ChecklistState | null | undefined): boolean {
  return !state?.dismissed_at && !state?.celebrated_at;
}

/** Where each item sends the user (settings deep links; QW-10 `?section=`). */
const ITEM_LINKS: Record<ChecklistItemId, string> = {
  connector: '/dashboard/settings?section=connectors',
  personality: '/dashboard/settings',
  voice: '/dashboard/settings',
  telegram: '/dashboard/settings',
  heartbeat: '/dashboard/settings',
  space: '/dashboard/settings',
  automation: '/dashboard/settings',
};

/** Live detection of each item — tolerant: a failed probe = not done. */
function useChecklistDetection(): Record<ChecklistItemId, boolean> {
  const { user } = useAuth();
  const { data: connectorsData } = useApiQuery<{ connectors?: unknown[] }>('/connectors', {
    componentName: 'StarterChecklistCard',
  });
  const { currentPersonalityId } = usePersonality();
  const { bindings } = useChannelBindings();
  const { settings: heartbeatSettings } = useHeartbeatSettings();
  const { spaces } = useSpaces();
  const { actions } = useScheduledActions();

  return {
    connector: (connectorsData?.connectors?.length ?? 0) > 0,
    personality: !!currentPersonalityId,
    voice: !!user?.voice_enabled || !!user?.voice_mode_enabled,
    telegram: (bindings?.length ?? 0) > 0,
    heartbeat: !!heartbeatSettings?.heartbeat_enabled,
    space: (spaces?.length ?? 0) > 0,
    automation: (actions?.length ?? 0) > 0,
  };
}

export function StarterChecklistCard() {
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  const { user } = useAuth();
  const { config } = useAppConfig();
  const state = (user?.onboarding_checklist ?? null) as ChecklistState | null;

  if (!shouldRenderChecklist(state)) return null;
  return <ChecklistBody lng={lng} t={t} config={config} />;
}

/** Inner body — mounted (and probing) only while the card is a candidate. */
function ChecklistBody({
  lng,
  t,
  config,
}: {
  lng: string;
  t: (key: string, opts?: Record<string, unknown>) => string;
  config: ReturnType<typeof useAppConfig>['config'];
}) {
  const flags: ChecklistFlags = {
    channels: !!config?.features?.channels_enabled,
    heartbeat: !!config?.features?.heartbeat_enabled,
    ragSpaces: !!config?.features?.rag_spaces_enabled,
  };
  const items = visibleChecklistItems(flags);
  const detection = useChecklistDetection();
  const doneCount = items.filter(id => detection[id]).length;
  const allDone = items.length > 0 && doneCount === items.length;

  const { mutate } = useApiMutation<{ dismissed?: boolean; celebrated?: boolean }, unknown>({
    method: 'PATCH',
    componentName: 'StarterChecklistCard',
  });
  const [gone, setGone] = useState(false);

  // Render-adjustment (official React pattern — never a setState in an
  // effect): remember that an INCOMPLETE list was seen; a later 100% is then
  // a live transition (discreet celebration line), otherwise the user was
  // already complete → silent persist, no retroactive fanfare. Probes still
  // loading count as "incomplete seen" — a fast pre-completed profile may
  // get the discreet line once; celebrated_at makes it at most once ever.
  const [sawIncomplete, setSawIncomplete] = useState(false);
  if (!allDone && !sawIncomplete) setSawIncomplete(true);
  const celebrating = allDone && sawIncomplete;
  const preCompleted = allDone && !sawIncomplete;

  // Persist-only effect (no setState): stamp celebrated_at exactly once.
  const persistedRef = useRef(false);
  useEffect(() => {
    if (!allDone || persistedRef.current) return;
    persistedRef.current = true;
    void mutate('/auth/me/onboarding-checklist', { celebrated: true }).catch(() => {
      // Best-effort: the card simply reappears next session.
    });
  }, [allDone, mutate]);

  const dismiss = () => {
    setGone(true);
    void mutate('/auth/me/onboarding-checklist', { dismissed: true }).catch(() => {
      // Best-effort: the card simply reappears next session.
    });
  };

  if (gone || preCompleted) return null;

  return (
    <section
      aria-labelledby="starter-checklist-heading"
      className="rounded-xl border border-border/40 bg-card/70 backdrop-blur-md px-4 py-3 shadow-sm"
    >
      <div className="flex items-center gap-2">
        <ListChecks className="h-4 w-4 shrink-0 text-primary" aria-hidden />
        <h3 id="starter-checklist-heading" className="flex-1 text-sm font-semibold">
          {t('dashboard.checklist.title')}
        </h3>
        <span
          role="progressbar"
          aria-valuenow={doneCount}
          aria-valuemin={0}
          aria-valuemax={items.length}
          aria-label={t('dashboard.checklist.progress_aria')}
          className="text-xs font-medium text-muted-foreground tabular-nums"
        >
          {t('dashboard.checklist.progress', { done: doneCount, total: items.length })}
        </span>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t('dashboard.checklist.dismiss')}
          className="p-1 rounded-full hover:bg-muted"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>
      {celebrating ? (
        <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
          <PartyPopper className="h-4 w-4 text-primary" aria-hidden />
          {t('dashboard.checklist.celebration')}
        </p>
      ) : (
        <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1" role="list">
          {items.map(id => (
            <li key={id} className="flex items-center gap-2 text-sm">
              {detection[id] ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              ) : (
                <Circle className="h-4 w-4 shrink-0 text-muted-foreground/50" aria-hidden />
              )}
              {detection[id] ? (
                <span className="text-muted-foreground line-through decoration-muted-foreground/40">
                  {t(`dashboard.checklist.items.${id}`)}
                </span>
              ) : (
                <Link
                  href={`/${lng}${ITEM_LINKS[id]}`}
                  className="text-foreground/90 hover:text-primary hover:underline"
                >
                  {t(`dashboard.checklist.items.${id}`)}
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

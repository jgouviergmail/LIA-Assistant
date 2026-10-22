'use client';

import { Loader2 } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import { rebuildBlockedReason } from '@/lib/discussion-context';
import type { Language } from '@/i18n/settings';
import {
  discussionActivitySchema,
  discussionSettingsSchema,
  type DiscussionActivity,
  type DiscussionSettings,
} from '@/types/proactive-discussions';

/** The first reason a requested rebuild cannot start, read from what the server published. */
function rebuildMessage(
  settings: DiscussionSettings,
  activity: DiscussionActivity | undefined,
  requested: boolean
): string | undefined {
  const blocked = rebuildBlockedReason(settings, activity);
  if (blocked) return blocked;
  if (activity?.rebuild === 'running') return 'discussions.rebuild_running';
  if (activity?.rebuild === 'requested' || requested) return 'discussions.rebuild_pending';
  return undefined;
}

/** A saved request is not evidence that the background producer can execute it. */
export function DiscussionRebuildStatus({
  lng,
  settings,
  activity,
  requested,
}: {
  lng: Language;
  settings: DiscussionSettings | undefined;
  /** What the server last reported; absent until the activity read returns. */
  activity?: DiscussionActivity;
  requested: boolean;
}) {
  const { t } = useTranslation(lng);
  const parsed = discussionSettingsSchema.safeParse(settings);
  if (!parsed.success) return requested ? <p role="status">{t('discussions.load_error')}</p> : null;
  const current = discussionActivitySchema.safeParse(activity);
  const state = current.success ? current.data : undefined;
  const message = rebuildMessage(parsed.data, state, requested);
  if (!message) return null;
  return (
    <p role="status" className="flex items-start gap-2 text-sm">
      {message === 'discussions.rebuild_running' && (
        <Loader2 aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 motion-safe:animate-spin" />
      )}
      <span className="min-w-0">{t(message)}</span>
    </p>
  );
}

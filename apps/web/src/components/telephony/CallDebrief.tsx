'use client';

/**
 * CallDebrief — the T01 structured debrief of a completed call.
 *
 * One component, two postures:
 *  - INFORMATIONAL (chat bubble): titled lists under the first-person report —
 *    the user answers the report naturally, no extra send plumbing;
 *  - ACTIONABLE (`actionable`, the settings calls surface): each follow-up
 *    carries a labelled control that PREFILLS the composer (`?draft=`), never one that
 *    sends.
 *
 * **Nothing here executes.** A debrief reports what someone else said on a
 * call the assistant placed, so an option, a surcharge or a commitment they
 * proposed is a claim to review — never an instruction. The follow-up chips
 * used `?intent=`, which is auto-sent (ADR-173), and `create_reminder_tool`
 * writes straight to the database with no HITL draft of its own: a chip
 * therefore created a reminder with no confirmation anywhere in the chain.
 *
 * Renders nothing for an empty/null debrief — absence, not noise.
 */

import {
  CalendarPlus,
  ClipboardList,
  Handshake,
  HelpCircle,
  ListPlus,
  PenLine,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { PhoneCallDebrief } from '@/types/telephony';
import type { LucideIcon } from 'lucide-react';

export interface CallDebriefProps {
  debrief: PhoneCallDebrief;
  /** URL locale segment — only consumed by the ACTIONABLE deep links. */
  lng?: string;
  /** When true, follow-ups carry composer-prefill controls (settings surface). */
  actionable?: boolean;
}

function hasContent(debrief: PhoneCallDebrief): boolean {
  return Boolean(
    debrief.key_points?.length ||
    debrief.commitments?.length ||
    debrief.follow_up_tasks?.length ||
    debrief.follow_up_reminders?.length ||
    debrief.follow_up_draft ||
    debrief.uncertainties?.length
  );
}

function DebriefList({
  icon: Icon,
  titleKey,
  items,
}: {
  icon: LucideIcon;
  titleKey: string;
  items: string[] | undefined;
}) {
  const { t } = useTranslation();
  if (!items?.length) return null;
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
        {t(titleKey)}
      </p>
      <ul className="mt-1 space-y-1" role="list">
        {items.map((item, index) => (
          <li
            key={`${index}-${item}`}
            className="text-sm text-foreground/90 [overflow-wrap:anywhere]"
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CallDebrief({ debrief, lng = 'fr', actionable = false }: CallDebriefProps) {
  const { t } = useTranslation();
  if (!hasContent(debrief)) return null;

  return (
    <div className="mt-2 min-w-0 space-y-4 rounded-lg border border-border/40 bg-muted/20 p-3">
      <DebriefList
        icon={ClipboardList}
        titleKey="settings.telephony.debrief.key_points"
        items={debrief.key_points}
      />
      <DebriefList
        icon={Handshake}
        titleKey="settings.telephony.debrief.commitments"
        items={debrief.commitments}
      />
      <DebriefList
        icon={ListPlus}
        titleKey="settings.telephony.debrief.tasks"
        items={debrief.follow_up_tasks}
      />
      <DebriefList
        icon={CalendarPlus}
        titleKey="settings.telephony.debrief.reminders"
        items={debrief.follow_up_reminders}
      />
      <DebriefList
        icon={HelpCircle}
        titleKey="settings.telephony.debrief.uncertainties"
        items={debrief.uncertainties}
      />
      {debrief.follow_up_draft && (
        <div>
          <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            <PenLine className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
            {t('settings.telephony.debrief.draft')}
          </p>
          <p className="mt-1 rounded-md border border-border/30 bg-background/60 p-2 text-sm italic text-foreground/80 [overflow-wrap:anywhere]">
            {debrief.follow_up_draft}
          </p>
        </div>
      )}
      {actionable && <CallDebriefActions debrief={debrief} lng={lng} />}
    </div>
  );
}

function FollowUpDrafts({
  items,
  intentKey,
  lng,
}: {
  items: string[] | undefined;
  intentKey: string;
  lng: string;
}) {
  const { t } = useTranslation();
  return items?.map((item, index) => {
    const sentence = t(intentKey, { item });
    const label = t('settings.telephony.debrief.prefill_aria', { sentence });
    return (
      <Button
        key={`${index}-${item}`}
        type="button"
        onClick={() => openChatDeepLink(chatDraftHref(lng, sentence))}
        className="h-auto min-h-11 w-full justify-start whitespace-normal px-3 py-2.5 text-left text-xs [overflow-wrap:anywhere]"
      >
        <PenLine aria-hidden="true" />
        <span className="min-w-0">{label}</span>
      </Button>
    );
  });
}

/** Draft-only follow-ups, placeable after all informational call blocks. */
export function CallDebriefActions({
  debrief,
  lng = 'fr',
}: Pick<CallDebriefProps, 'debrief' | 'lng'>) {
  const { t } = useTranslation();
  if (
    !debrief.follow_up_tasks?.length &&
    !debrief.follow_up_reminders?.length &&
    !debrief.follow_up_draft
  )
    return null;

  return (
    <div className="space-y-2 border-t border-border/50 pt-3">
      <FollowUpDrafts
        items={debrief.follow_up_tasks}
        intentKey="settings.telephony.debrief.intent_task"
        lng={lng}
      />
      <FollowUpDrafts
        items={debrief.follow_up_reminders}
        intentKey="settings.telephony.debrief.intent_reminder"
        lng={lng}
      />
      {debrief.follow_up_draft && (
        <Button
          type="button"
          onClick={() =>
            openChatDeepLink(
              chatDraftHref(
                lng,
                t('settings.telephony.debrief.draft_prefill', {
                  draft: debrief.follow_up_draft,
                })
              )
            )
          }
          className="h-auto min-h-11 w-full justify-start whitespace-normal px-3 py-2.5 text-left text-xs [overflow-wrap:anywhere]"
        >
          <PenLine aria-hidden="true" />
          {t('settings.telephony.debrief.use_draft')}
        </Button>
      )}
    </div>
  );
}

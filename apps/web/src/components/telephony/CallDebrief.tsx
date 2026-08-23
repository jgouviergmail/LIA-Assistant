'use client';

/**
 * CallDebrief — the T01 structured debrief of a completed call.
 *
 * One component, two postures:
 *  - INFORMATIONAL (chat bubble): titled lists under the first-person report —
 *    the user answers the report naturally, no extra send plumbing;
 *  - ACTIONABLE (`actionable`, the settings calls surface): each follow-up
 *    carries a chip that PREFILLS the composer (`?draft=`), never one that
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

import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { PhoneCallDebrief } from '@/types/telephony';
import type { LucideIcon } from 'lucide-react';

export interface CallDebriefProps {
  debrief: PhoneCallDebrief;
  /** URL locale segment — only consumed by the ACTIONABLE deep links. */
  lng?: string;
  /** When true, follow-ups carry composer-prefill chips (settings surface). */
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
  itemAction,
}: {
  icon: LucideIcon;
  titleKey: string;
  items: string[] | undefined;
  /** Per-item action chip (actionable posture only). */
  itemAction?: (item: string) => { label: string; onSelect: () => void } | null;
}) {
  const { t } = useTranslation();
  if (!items?.length) return null;
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {t(titleKey)}
      </p>
      <ul className="mt-1 space-y-1" role="list">
        {items.map(item => {
          const action = itemAction?.(item) ?? null;
          // The name states what the CLICK does, not what the sentence says.
          // "Create a task: …" alone promised the creation; the click only
          // puts that sentence in the composer.
          const name = action
            ? t('settings.telephony.debrief.prefill_aria', {
                sentence: action.label,
              })
            : '';
          return (
            <li key={item} className="flex items-start gap-1.5 text-sm text-foreground/90">
              <span className="min-w-0 flex-1">{item}</span>
              {action && (
                <button
                  type="button"
                  onClick={action.onSelect}
                  aria-label={name}
                  title={name}
                  className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-primary hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {/* A pen, not a paper plane: the click writes a draft. The
                      send icon promised a departure that never happened. */}
                  <PenLine className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function CallDebrief({ debrief, lng = 'fr', actionable = false }: CallDebriefProps) {
  const { t } = useTranslation();
  if (!hasContent(debrief)) return null;

  /**
   * A follow-up chip PREFILLS the composer — it never sends.
   *
   * A debrief reports what someone else said on a call the assistant placed:
   * an option, a surcharge or a commitment they proposed is a claim to review,
   * never an instruction. `?intent=` is auto-sent (ADR-173), and
   * `create_reminder_tool` writes straight to the database with no HITL draft
   * of its own — so a reminder chip used to create the reminder with no
   * confirmation anywhere in the chain. Prose alone cannot promise which tool
   * the planner will pick either, so "that tool has its own draft" was never a
   * guarantee this card could rely on.
   *
   * `?draft=` puts the sentence in the composer and stops. Tool-level HITL
   * still applies once the user presses Enter — this adds a step, it removes
   * none.
   */
  const prefillChip = (intentKey: string) =>
    actionable
      ? (item: string) => {
          const sentence = t(intentKey, { item });
          return {
            label: sentence,
            onSelect: () => openChatDeepLink(chatDraftHref(lng, sentence)),
          };
        }
      : undefined;

  return (
    <div className="mt-2 space-y-3 rounded-lg border border-border/40 bg-muted/20 p-3">
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
        itemAction={prefillChip('settings.telephony.debrief.intent_task')}
      />
      <DebriefList
        icon={CalendarPlus}
        titleKey="settings.telephony.debrief.reminders"
        items={debrief.follow_up_reminders}
        itemAction={prefillChip('settings.telephony.debrief.intent_reminder')}
      />
      <DebriefList
        icon={HelpCircle}
        titleKey="settings.telephony.debrief.uncertainties"
        items={debrief.uncertainties}
      />
      {debrief.follow_up_draft && (
        <div>
          <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            <PenLine className="h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.telephony.debrief.draft')}
          </p>
          <p className="mt-1 rounded-md border border-border/30 bg-background/60 p-2 text-sm italic text-foreground/80">
            {debrief.follow_up_draft}
          </p>
          {actionable && (
            <button
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
              className="mt-1.5 text-xs font-medium text-primary underline underline-offset-2 hover:text-primary/80"
            >
              {t('settings.telephony.debrief.use_draft')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

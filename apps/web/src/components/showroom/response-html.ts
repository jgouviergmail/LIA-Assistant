/**
 * Synthetic rich replies for the guided showroom missions.
 *
 * Each mission ends with LIA's answer rendered by the PRODUCTION rich-HTML
 * pipeline (`MarkdownContent` → rehypeRaw → rehypeSanitize) using the exact
 * component vocabulary of the HTML response directive (ADR-177):
 * `lia-response`, `lia-callout`, `lia-chip`, `lia-kv`, `lia-steps`,
 * `lia-stats`, `lia-collapsible`. The markup lives ONCE here — locales only
 * carry text — and every interpolated string is HTML-escaped before
 * composition (the sanitize pass remains the real boundary; escaping keeps
 * the storyboard text intact rather than stripped).
 *
 * Honesty contract: the reply reflects the visitor's decisions. A refusal
 * reads as a respected outcome, never as an error, and a refused effect is
 * never described as applied.
 *
 * Voice contract (owner arbitration 2026-08-06): the reply speaks as the
 * assistant would in a REAL exchange — task tone, no product talk. Anything
 * pedagogical ("memory is editable in settings", "calls are always gated")
 * lives in the separate MissionDemoNote bubble, never in this HTML. The
 * only callouts left here are task content (the 10:00 deadline, the agenda
 * overlap).
 */

import type { TFunction } from 'i18next';

import type { ShowroomDecisionKind, ShowroomMissionId } from '@/components/showroom/types';

type Decisions = readonly (ShowroomDecisionKind | null)[];

/** Escape interpolated text nodes (markup stays code-owned). */
function esc(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

type ChipTone = 'green' | 'amber' | 'indigo';

const CHIP_ICON: Record<ChipTone, string> = {
  green: 'check_circle',
  amber: 'block',
  indigo: 'event',
};

function chip(tone: ChipTone, label: string): string {
  return (
    `<span class="lia-chip lia-chip--${tone}">` +
    `<span class="material-symbols-outlined">${CHIP_ICON[tone]}</span>` +
    `${esc(label)}</span>`
  );
}

/** One chip per decided step: green confirm, indigo edit, amber refusal. */
function decisionChip(
  decision: ShowroomDecisionKind | null,
  labels: { confirm: string; edit?: string; cancel: string }
): string {
  if (decision === 'cancel') return chip('amber', labels.cancel);
  if (decision === 'edit') return chip('indigo', labels.edit ?? labels.confirm);
  return chip('green', labels.confirm);
}

function kv(rows: readonly { label: string; value: string }[]): string {
  const body = rows
    .map(r => `<dt>${esc(r.label)}</dt><dd><strong>${esc(r.value)}</strong></dd>`)
    .join('');
  return `<dl class="lia-kv">${body}</dl>`;
}

function callout(variant: 'info' | 'success' | 'warning', title: string, body: string): string {
  return (
    `<div class="lia-callout lia-callout-${variant}">` +
    `<p class="lia-callout__title">${esc(title)}</p>` +
    `<p>${esc(body)}</p></div>`
  );
}

function steps(items: readonly string[]): string {
  return `<ol class="lia-steps">${items.map(s => `<li>${esc(s)}</li>`).join('')}</ol>`;
}

function stats(items: readonly { value: string; label: string }[]): string {
  const tiles = items
    .map(
      s =>
        `<div class="lia-stat"><span class="lia-stat__value">${esc(s.value)}</span>` +
        `<span class="lia-stat__label">${esc(s.label)}</span></div>`
    )
    .join('');
  return `<div class="lia-stats">${tiles}</div>`;
}

function collapsible(summary: string, lines: readonly string[]): string {
  const body = lines.map(l => `<p>${esc(l)}</p>`).join('');
  return `<details class="lia-collapsible"><summary>${esc(summary)}</summary>${body}</details>`;
}

function chipRow(chips: readonly string[]): string {
  return `<p>${chips.join(' ')}</p>`;
}

function wrap(...blocks: readonly string[]): string {
  return `<div class="lia-response">\n${blocks.join('\n')}\n</div>`;
}

// ---------------------------------------------------------------------------
// Per-mission replies (keys under showroom.m.<id>.response.*)
// ---------------------------------------------------------------------------

function overloadedMorning(t: TFunction, d: Decisions): string {
  const k = 'showroom.m.overloaded_morning.response';
  return wrap(
    `<p>${esc(t(`${k}.intro`))}</p>`,
    chipRow([
      decisionChip(d[0], {
        confirm: t(`${k}.chip_email_confirm`),
        edit: t(`${k}.chip_email_edit`),
        cancel: t(`${k}.chip_email_cancel`),
      }),
      decisionChip(d[1], {
        confirm: t(`${k}.chip_calendar_confirm`),
        cancel: t(`${k}.chip_calendar_cancel`),
      }),
    ]),
    kv([
      { label: t(`${k}.kv_focus_label`), value: t(`${k}.kv_focus_value`) },
      { label: t(`${k}.kv_checkpoint_label`), value: t(`${k}.kv_checkpoint_value`) },
      { label: t(`${k}.kv_deadline_label`), value: t(`${k}.kv_deadline_value`) },
    ]),
    callout('success', t(`${k}.callout_title`), t(`${k}.callout_body`)),
    `<p>${esc(t(`${k}.closing`))}</p>`
  );
}

function proactiveAlert(t: TFunction, d: Decisions): string {
  const k = 'showroom.m.proactive_alert.response';
  return wrap(
    `<p>${esc(t(`${k}.intro`))}</p>`,
    chipRow([
      decisionChip(d[0], {
        confirm: t(`${k}.chip_run_confirm`),
        cancel: t(`${k}.chip_run_cancel`),
      }),
      decisionChip(d[1], {
        confirm: t(`${k}.chip_marc_confirm`),
        edit: t(`${k}.chip_marc_edit`),
        cancel: t(`${k}.chip_marc_cancel`),
      }),
    ]),
    kv([
      { label: t(`${k}.kv_next_label`), value: t(`${k}.kv_next_value`) },
      { label: t(`${k}.kv_quiet_label`), value: t(`${k}.kv_quiet_value`) },
    ]),
    `<p>${esc(t(`${k}.closing`))}</p>`
  );
}

function memoryDinner(t: TFunction, d: Decisions): string {
  const k = 'showroom.m.memory_dinner.response';
  return wrap(
    `<p>${esc(t(`${k}.intro`))}</p>`,
    kv([
      { label: t(`${k}.kv_place_label`), value: t(`${k}.kv_place_value`) },
      { label: t(`${k}.kv_when_label`), value: t(`${k}.kv_when_value`) },
      { label: t(`${k}.kv_recall_label`), value: t(`${k}.kv_recall_value`) },
    ]),
    chipRow([
      decisionChip(d[0], {
        confirm: t(`${k}.chip_invite_confirm`),
        edit: t(`${k}.chip_invite_edit`),
        cancel: t(`${k}.chip_invite_cancel`),
      }),
      decisionChip(d[1], {
        confirm: t(`${k}.chip_event_confirm`),
        cancel: t(`${k}.chip_event_cancel`),
      }),
    ]),
    `<p>${esc(t(`${k}.closing`))}</p>`
  );
}

function phoneBooking(t: TFunction, d: Decisions): string {
  const k = 'showroom.m.phone_booking.response';
  if (d[0] === 'cancel') {
    return wrap(
      `<p>${esc(t(`${k}.intro_cancel`))}</p>`,
      chipRow([chip('amber', t(`${k}.chip_cancel`))])
    );
  }
  return wrap(
    `<p>${esc(t(`${k}.intro_confirm`))}</p>`,
    kv([
      { label: t(`${k}.kv_place_label`), value: t(`${k}.kv_place_value`) },
      { label: t(`${k}.kv_result_label`), value: t(`${k}.kv_result_value`) },
      { label: t(`${k}.kv_when_label`), value: t(`${k}.kv_when_value`) },
    ]),
    chipRow([chip('green', t(`${k}.chip_confirm`))]),
    collapsible(t(`${k}.transcript_summary`), [
      t(`${k}.transcript_1`),
      t(`${k}.transcript_2`),
      t(`${k}.transcript_3`),
    ]),
    `<p>${esc(t(`${k}.closing_confirm`))}</p>`
  );
}

function dailyBriefing(t: TFunction, d: Decisions): string {
  const k = 'showroom.m.daily_briefing.response';
  return wrap(
    `<p>${esc(t(`${k}.intro`))}</p>`,
    stats([
      { value: '5', label: t(`${k}.stat_emails`) },
      { value: '3', label: t(`${k}.stat_meetings`) },
      { value: '2', label: t(`${k}.stat_tasks`) },
    ]),
    `<h3>${esc(t(`${k}.agenda_title`))}</h3>`,
    kv([
      { label: '09:00', value: t(`${k}.meeting_1`) },
      { label: '14:00', value: t(`${k}.meeting_2`) },
      { label: '15:30', value: t(`${k}.meeting_3`) },
    ]),
    callout('warning', t(`${k}.overlap_title`), t(`${k}.overlap_body`)),
    chipRow([
      decisionChip(d[0], {
        confirm: t(`${k}.chip_focus_confirm`),
        cancel: t(`${k}.chip_focus_cancel`),
      }),
    ]),
    `<p>${esc(t(`${k}.closing`))}</p>`
  );
}

function configTour(t: TFunction, d: Decisions): string {
  const k = 'showroom.m.config_tour.response';
  return wrap(
    `<p>${esc(t(`${k}.intro`))}</p>`,
    steps([t(`${k}.step_1`), t(`${k}.step_2`)]),
    chipRow([
      decisionChip(d[0], {
        confirm: t(`${k}.chip_concise_confirm`),
        cancel: t(`${k}.chip_concise_cancel`),
      }),
      decisionChip(d[1], {
        confirm: t(`${k}.chip_mornings_confirm`),
        cancel: t(`${k}.chip_mornings_cancel`),
      }),
    ]),
    `<p>${esc(t(`${k}.closing`))}</p>`
  );
}

const BUILDERS: Record<ShowroomMissionId, (t: TFunction, d: Decisions) => string> = {
  overloaded_morning: overloadedMorning,
  proactive_alert: proactiveAlert,
  memory_dinner: memoryDinner,
  phone_booking: phoneBooking,
  daily_briefing: dailyBriefing,
  config_tour: configTour,
};

/** Build the mission's synthetic rich reply (a `lia-response` HTML string). */
export function buildShowroomResponseHtml(
  id: ShowroomMissionId,
  t: TFunction,
  decisions: Decisions
): string {
  return BUILDERS[id](t, decisions);
}

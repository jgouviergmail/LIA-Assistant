/**
 * Fictional personal-assistant results rendered by the production HTML pipeline.
 * Source conflicts remain visible. Decisions describe only the local simulation;
 * an edit instruction never claims a regenerated draft or a completed action.
 */
import type { TFunction } from 'i18next';
import { getShowroomMission } from '@/components/showroom/missions';
import type { ShowroomDecisionKind, ShowroomMissionId } from '@/components/showroom/types';

type Decisions = readonly (ShowroomDecisionKind | null)[];

function esc(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function chip(decision: ShowroomDecisionKind): string {
  const tone = decision === 'cancel' ? 'amber' : decision === 'edit' ? 'indigo' : 'green';
  const icon =
    decision === 'confirm' ? 'check_circle' : decision === 'edit' ? 'edit_note' : 'block';
  return `<span class="lia-chip lia-chip--${tone}"><span class="material-symbols-outlined">${icon}</span>`;
}

function decisionRows(id: ShowroomMissionId, t: TFunction, decisions: Decisions): string {
  const rows = getShowroomMission(id).decisions.flatMap((spec, index) => {
    const decision = decisions[index];
    if (!decision) return [];
    return [
      `<dt>${esc(t(spec.receiptLabelKey))}</dt><dd>${chip(decision)}${esc(t(`showroom.personal.${decision}`))}</span></dd>`,
    ];
  });
  return rows.length ? `<dl class="lia-kv">${rows.join('')}</dl>` : '';
}

interface ResultRow {
  label: string;
  value: string;
}

function keyValues(rows: ResultRow[]): string {
  return `<dl class="lia-kv">${rows.map(row => `<dt>${esc(row.label)}</dt><dd>${esc(row.value)}</dd>`).join('')}</dl>`;
}

/** The native response vocabulary makes each result easy to scan on its own. */
function resultBody(id: ShowroomMissionId, rows: ResultRow[]): string {
  if (id === 'daily_briefing') {
    return `<ol class="lia-steps">${rows.map(row => `<li><strong>${esc(row.label)}</strong><p>${esc(row.value)}</p></li>`).join('')}</ol>`;
  }
  if (id === 'config_tour') {
    return rows.map(row => `<h3>${esc(row.label)}</h3><p>${esc(row.value)}</p>`).join('');
  }
  if (id === 'overloaded_morning') {
    const warning = rows[1];
    return `${keyValues([rows[0], rows[2]])}<div class="lia-callout lia-callout-warning"><p class="lia-callout__title">${esc(warning.label)}</p><p>${esc(warning.value)}</p></div>`;
  }
  return keyValues(rows);
}

export function buildShowroomResponseHtml(
  id: ShowroomMissionId,
  t: TFunction,
  decisions: Decisions
): string {
  const key = `showroom.personal.${id}`;
  const choices = decisionRows(id, t, decisions);
  // No simulated call outcome is shown after a refusal or edit request.
  if (id === 'phone_booking' && decisions[0] !== 'confirm') {
    return `<div class="lia-response">${choices}</div>`;
  }
  const rows = [1, 2, 3].map(index => ({
    label: t(`${key}.label_${index}`),
    value: t(`${key}.value_${index}`),
  }));
  return `<div class="lia-response">\n<p>${esc(t(`${key}.intro`))}</p>\n${resultBody(id, rows)}\n${choices}\n<p>${esc(t(`${key}.closing`))}</p>\n</div>`;
}

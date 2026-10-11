/** Rich results preserve uncertainty and never claim a declined action. */
import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import { SHOWROOM_MISSIONS } from '@/components/showroom/missions';
import { buildShowroomResponseHtml } from '@/components/showroom/response-html';
import type { ShowroomDecisionKind, ShowroomMissionDefinition } from '@/components/showroom/types';

const t = ((key: string) => key) as TFunction;
function combos(def: ShowroomMissionDefinition): ShowroomDecisionKind[][] {
  return def.decisions.reduce<ShowroomDecisionKind[][]>(
    (acc, spec) => acc.flatMap(prefix => spec.allowed.map(kind => [...prefix, kind])),
    [[]]
  );
}

describe.each(SHOWROOM_MISSIONS.map(m => [m.id, m] as const))('rich reply — %s', (id, def) => {
  it('renders every decision combination through the sanitized HTML vocabulary', () => {
    for (const combo of combos(def)) {
      const html = buildShowroomResponseHtml(id, t, combo);
      expect(html.startsWith('<div class="lia-response">')).toBe(true);
      expect(html.endsWith('</div>')).toBe(true);
      expect(html).not.toMatch(/style\s*=|<script|https?:|:\/\//);
      for (const cls of [...html.matchAll(/class="([^"]+)"/g)].flatMap(m => m[1].split(/\s+/))) {
        expect(cls).toMatch(/^(lia-|material-symbols-outlined)/);
      }
    }
  });

  it('a refused action never shows its approved outcome', () => {
    const html = buildShowroomResponseHtml(
      id,
      t,
      def.decisions.map(() => 'cancel')
    );
    for (const spec of def.decisions) {
      expect(html).not.toContain(spec.outcome.confirm);
    }
    expect(html).not.toContain('lia-chip--green');
    if (def.decisions.length) expect(html).toContain('lia-chip--amber');
  });

  it('read-only results have no invented approvals', () => {
    if (def.decisions.length) return;
    const html = buildShowroomResponseHtml(id, t, []);
    expect(html).not.toContain('lia-chip');
    expect(html).toContain(`showroom.personal.${id}.value_3`);
  });
});

describe('rich reply — personal-assistant cases', () => {
  it('Radio reads as a programme, meetings as minutes, and the price conflict as a warning', () => {
    expect(buildShowroomResponseHtml('daily_briefing', t, [])).toContain('lia-steps');
    expect(buildShowroomResponseHtml('config_tour', t, [])).toContain('<h3>');
    expect(buildShowroomResponseHtml('overloaded_morning', t, ['cancel', 'cancel'])).toContain(
      'lia-callout-warning'
    );
  });
  it('escapes hostile text before the production sanitize boundary', () => {
    const hostile = ((key: string) =>
      key.endsWith('.intro') ? '<img src=x onerror=alert(1)>' : key) as TFunction;
    const html = buildShowroomResponseHtml('overloaded_morning', hostile, ['confirm', 'cancel']);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('an edit instruction shows no applied email outcome', () => {
    const html = buildShowroomResponseHtml('overloaded_morning', t, ['edit', 'cancel']);
    expect(html).toContain('showroom.personal.edit');
    expect(html).not.toContain('showroom.receipt.email_applied');
    expect(html).toContain('lia-chip--indigo');
  });

  it.each(['cancel', 'edit'] as const)(
    'a %s call shows no fictional successful-call summary',
    decision => {
      const html = buildShowroomResponseHtml('phone_booking', t, [decision]);
      expect(html).not.toContain('showroom.personal.phone_booking.value_2');
      expect(html).not.toContain('showroom.personal.phone_booking.value_3');
      expect(html).not.toContain('lia-chip--green');
    }
  );

  it('a confirmed call labels its illustrative summary', () => {
    const html = buildShowroomResponseHtml('phone_booking', t, ['confirm']);
    expect(html).toContain('showroom.personal.phone_booking.intro');
    expect(html).toContain('showroom.personal.phone_booking.value_2');
  });
});

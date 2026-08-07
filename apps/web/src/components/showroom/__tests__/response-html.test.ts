/**
 * Synthetic rich replies (response-html).
 *
 * What must hold, for EVERY mission and decision combination:
 * - the reply is a `lia-response`-wrapped HTML string using ONLY the
 *   directive vocabulary (ADR-177 classes);
 * - the reply reflects decisions honestly: a refused step renders its amber
 *   refusal chip and NEVER its confirm/edit label; an edited draft renders
 *   the indigo edited chip;
 * - interpolated text is HTML-escaped (markup stays code-owned);
 * - no URL, provider name, or secret shape ever appears.
 */

import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';

import { SHOWROOM_MISSIONS } from '@/components/showroom/missions';
import { buildShowroomResponseHtml } from '@/components/showroom/response-html';
import type {
  ShowroomDecisionKind,
  ShowroomMissionDefinition,
} from '@/components/showroom/types';

// Identity translator — outputs read as keys, so chip assertions are exact.
const t = ((key: string) => key) as TFunction;

function combos(def: ShowroomMissionDefinition): ShowroomDecisionKind[][] {
  return def.decisions.reduce<ShowroomDecisionKind[][]>(
    (acc, spec) => acc.flatMap((p) => spec.allowed.map((k) => [...p, k])),
    [[]]
  );
}

describe.each(SHOWROOM_MISSIONS.map((m) => [m.id, m] as const))(
  'rich reply — %s',
  (id, def) => {
    it('wraps every combination in a lia-response envelope', () => {
      for (const combo of combos(def)) {
        const html = buildShowroomResponseHtml(id, t, combo);
        expect(html.startsWith('<div class="lia-response">')).toBe(true);
        expect(html.endsWith('</div>')).toBe(true);
      }
    });

    it('renders a refusal as an amber chip, never as applied', () => {
      // All-cancel where allowed; otherwise first allowed kind.
      const combo = def.decisions.map((s) =>
        s.allowed.includes('cancel') ? ('cancel' as const) : s.allowed[0]
      );
      const html = buildShowroomResponseHtml(id, t, combo);
      expect(html).toContain('lia-chip--amber');
      expect(html).not.toContain('lia-chip--green');
    });

    it('renders the all-confirm path with green chips and no amber', () => {
      const combo = def.decisions.map(() => 'confirm' as const);
      const html = buildShowroomResponseHtml(id, t, combo);
      expect(html).toContain('lia-chip--green');
      expect(html).not.toContain('lia-chip--amber');
    });

    it('stays inside the directive vocabulary and clean of foreign tokens', () => {
      const html = buildShowroomResponseHtml(
        id,
        t,
        def.decisions.map((s) => s.allowed[0])
      );
      // Only directive classes (ADR-177) — no widget-card classes, no styles.
      expect(html).not.toMatch(/style\s*=/);
      expect(html).not.toMatch(/<script/i);
      expect(html).not.toMatch(/https?:|:\/\//);
      const classes = [...html.matchAll(/class="([^"]+)"/g)].flatMap((m) =>
        m[1].split(/\s+/)
      );
      for (const cls of classes) {
        expect(cls).toMatch(/^(lia-|material-symbols-outlined)/);
      }
    });
  }
);

describe('rich reply — cross-cutting', () => {
  it('escapes interpolated text nodes', () => {
    const hostile = ((key: string) =>
      key.endsWith('.intro') ? '<img src=x onerror=alert(1)>' : key) as TFunction;
    const html = buildShowroomResponseHtml('overloaded_morning', hostile, [
      'confirm',
      'confirm',
    ]);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('renders an edited draft as the indigo edited chip', () => {
    const html = buildShowroomResponseHtml('overloaded_morning', t, [
      'edit',
      'confirm',
    ]);
    expect(html).toContain('lia-chip--indigo');
    expect(html).toContain(
      'showroom.m.overloaded_morning.response.chip_email_edit'
    );
  });

  it('the phone mission branches on the call decision', () => {
    const confirmed = buildShowroomResponseHtml('phone_booking', t, ['confirm']);
    expect(confirmed).toContain('lia-collapsible');
    expect(confirmed).toContain(
      'showroom.m.phone_booking.response.transcript_1'
    );
    const refused = buildShowroomResponseHtml('phone_booking', t, ['cancel']);
    expect(refused).not.toContain('lia-collapsible');
    expect(refused).toContain('showroom.m.phone_booking.response.intro_cancel');
    // A refused call never shows the confirmed reservation summary.
    expect(refused).not.toContain(
      'showroom.m.phone_booking.response.kv_result_value'
    );
  });

  it('the briefing renders its stat tiles and overlap warning', () => {
    const html = buildShowroomResponseHtml('daily_briefing', t, ['confirm']);
    expect(html).toContain('lia-stats');
    expect(html).toContain('lia-callout-warning');
    expect(html).toContain('<h3>');
  });

  it('the config tour renders its two steps', () => {
    const html = buildShowroomResponseHtml('config_tour', t, [
      'confirm',
      'cancel',
    ]);
    expect(html).toContain('lia-steps');
    expect(html).toContain('showroom.m.config_tour.response.step_1');
    expect(html).toContain('showroom.m.config_tour.response.chip_mornings_cancel');
  });
});

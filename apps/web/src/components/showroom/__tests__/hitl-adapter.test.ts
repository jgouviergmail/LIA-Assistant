/**
 * Pure adapters from showroom decision specs to the EXISTING HITL and
 * trace contracts (no fork of HitlActionCard / ExecutionTraceDisclosure).
 *
 * What must hold:
 * - a draft spec → draft_critique card with the spec's allowed actions and a
 *   non-null synthetic messageId (the inline edit toggle requires it);
 * - a tool spec → tool_confirmation card with confirm/cancel ONLY and
 *   translated arg labels/values (literal or i18n-resolved);
 * - adapters expose fixed synthetic fields only — never prompt,
 *   system_message, chain_of_thought, api_key, token, or the whole fixture;
 * - the public trace has four localized-label slots, bounded categories,
 *   a deterministic caller-supplied duration, and reasoning === '';
 * - resolveCard maps decisions onto the card lifecycle without new states.
 */

import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';

import {
  buildDecisionCard,
  buildShowroomTrace,
  resolveCard,
} from '@/components/showroom/hitl-adapter';
import { getShowroomMission } from '@/components/showroom/missions';

// Identity translator: assertions read as keys, no i18n in this layer.
const t = ((key: string) => key) as TFunction;

const MORNING = getShowroomMission('overloaded_morning');
const PHONE = getShowroomMission('phone_booking');

describe('showroom hitl-adapter', () => {
  it('builds a draft_critique card from a draft spec', () => {
    const card = buildDecisionCard(2, MORNING.id, MORNING.decisions[0], t);
    expect(card.status).toBe('awaiting');
    expect(card.resolution).toBeNull();
    const payload = card.payload;
    expect(payload).not.toBeNull();
    if (payload?.kind !== 'draft_critique') throw new Error('wrong card kind');
    // Non-null synthetic id — HitlActionCard's edit toggle compares it.
    expect(payload.messageId).toBe('showroom-overloaded_morning-email_reply-2');
    expect(payload.actions.map((a) => a.action)).toEqual([
      'confirm',
      'edit',
      'cancel',
    ]);
    expect(payload.draftContent).toEqual({
      to: 'emma@atlas.example.invalid',
      subject: 'showroom.proposals.email_subject',
      body: 'showroom.proposals.email_body',
    });
  });

  it('builds a tool_confirmation card from a tool spec', () => {
    const card = buildDecisionCard(1, MORNING.id, MORNING.decisions[1], t);
    const payload = card.payload;
    if (payload?.kind !== 'tool_confirmation') throw new Error('wrong card kind');
    expect(payload.messageId).toBe(
      'showroom-overloaded_morning-calendar_adjustment-1'
    );
    expect(payload.actions.map((a) => a.action)).toEqual(['confirm', 'cancel']);
    // Literal arg values pass through; labels resolve through t.
    expect(payload.toolArgs).toEqual({
      'showroom.proposals.from': '07:30',
      'showroom.proposals.to': '10:30',
    });
  });

  it('resolves valueKey args through the translator', () => {
    const card = buildDecisionCard(1, PHONE.id, PHONE.decisions[0], t);
    const payload = card.payload;
    if (payload?.kind !== 'tool_confirmation') throw new Error('wrong card kind');
    expect(payload.toolArgs).toEqual({
      'showroom.m.phone_booking.decisions.authorize_call.callee':
        'showroom.m.phone_booking.decisions.authorize_call.callee_value',
      'showroom.m.phone_booking.decisions.authorize_call.goal':
        'showroom.m.phone_booking.decisions.authorize_call.goal_value',
    });
  });

  it('exposes only bounded display fields — never prompt or secret shapes', () => {
    for (const spec of [...MORNING.decisions, ...PHONE.decisions]) {
      const card = buildDecisionCard(3, MORNING.id, spec, t);
      const serialized = JSON.stringify(card).toLowerCase();
      for (const forbidden of [
        'prompt',
        'system_message',
        'chain_of_thought',
        'api_key',
        'token',
      ]) {
        expect(serialized).not.toContain(forbidden);
      }
    }
  });

  it.each([
    ['confirm', 'confirmed', 'confirm'],
    ['edit', 'confirmed', 'confirm'],
    ['cancel', 'cancelled', 'cancel'],
  ] as const)(
    'resolveCard maps %s onto the existing lifecycle',
    (decision, resolution, submitted) => {
      const card = buildDecisionCard(1, MORNING.id, MORNING.decisions[0], t);
      const resolved = resolveCard(card, decision);
      expect(resolved.status).toBe('resolved');
      expect(resolved.resolution).toBe(resolution);
      expect(resolved.submittedAction).toBe(submitted);
      // The pending card is not mutated.
      expect(card.status).toBe('awaiting');
    }
  );

  it('builds the bounded four-slot public trace with empty reasoning', () => {
    const trace = buildShowroomTrace(['a', 'b', 'c', 'd'], 6100);
    expect(trace.steps).toHaveLength(4);
    expect(trace.steps.map((s) => s.category)).toEqual([
      'system',
      'context',
      'agent',
      'tool',
    ]);
    expect(trace.steps.map((s) => s.label)).toEqual(['a', 'b', 'c', 'd']);
    expect(trace.reasoning).toBe('');
    expect(trace.durationMs).toBe(6100);
  });

  it('refuses a trace with fewer labels than slots', () => {
    expect(() => buildShowroomTrace(['only', 'three', 'labels'], 1000)).toThrow(
      /needs 4 labels/
    );
  });
});

/**
 * Synthetic mission fixtures — every registered mission.
 *
 * What must hold, for EVERY mission definition:
 * - versioned (`<id>-vN`) and immutable (deep-frozen at module load);
 * - 3..4 read sources, 1..3 decisions with valid `allowed` lists (edit only
 *   on drafts) and complete outcome keys (drafts carry the edit outcome);
 * - every email-like identifier lives on example.invalid;
 * - no URL, secret-like key, local path, shell command, provider name, or
 *   Date.now-derived value — definitions are pure static data;
 * - user-facing texts are i18n keys, structural facts are bounded literals.
 *
 * Registry completeness: the frontend mission ids mirror the telemetry
 * vocabulary (SHOWROOM_MISSION_IDS) — a mission cannot exist without its two
 * bounded per-mission funnel events, and vice versa.
 */

import { describe, expect, it } from 'vitest';

import {
  getShowroomMission,
  SHOWROOM_MISSIONS,
} from '@/components/showroom/missions';
import { SHOWROOM_MISSION_IDS } from '@/lib/product-telemetry';

function collectStrings(value: unknown, out: string[] = []): string[] {
  if (typeof value === 'string') {
    out.push(value);
  } else if (Array.isArray(value)) {
    for (const item of value) collectStrings(item, out);
  } else if (value !== null && typeof value === 'object') {
    for (const item of Object.values(value)) collectStrings(item, out);
  }
  return out;
}

function assertDeeplyFrozen(value: unknown, path = 'root'): void {
  if (value !== null && typeof value === 'object') {
    expect(Object.isFrozen(value), `${path} must be frozen`).toBe(true);
    for (const [key, item] of Object.entries(value)) {
      assertDeeplyFrozen(item, `${path}.${key}`);
    }
  }
}

const FORBIDDEN =
  /https?:|:\/\/|www\.|sk-[a-zA-Z0-9]|api[_-]?key|\/home\/|\/Users\/|[A-Z]:\\|sudo |rm -|curl |openai|anthropic|gemini|deepseek|qwen|ollama|perplexity/i;

describe('mission registry', () => {
  it('mirrors the bounded telemetry mission ids, in full', () => {
    expect(SHOWROOM_MISSIONS.map((m) => m.id).sort()).toEqual(
      [...SHOWROOM_MISSION_IDS].sort()
    );
  });

  it('resolves every id and throws on an unknown one', () => {
    for (const id of SHOWROOM_MISSION_IDS) {
      expect(getShowroomMission(id).id).toBe(id);
    }
    expect(() =>
      getShowroomMission('nope' as (typeof SHOWROOM_MISSION_IDS)[number])
    ).toThrow(/unknown showroom mission/);
  });
});

describe.each(SHOWROOM_MISSIONS.map((m) => [m.id, m] as const))(
  'mission fixture — %s',
  (id, def) => {
    const strings = collectStrings(def);

    it('carries a versioned fixture id', () => {
      expect(def.fixtureVersion).toMatch(new RegExp(`^${id}-v\\d+$`));
    });

    it('is deeply frozen', () => {
      assertDeeplyFrozen(def);
    });

    it('exposes 3..4 sources and 1..3 in-order decisions', () => {
      expect(def.sources.length).toBeGreaterThanOrEqual(3);
      expect(def.sources.length).toBeLessThanOrEqual(4);
      expect(def.decisions.length).toBeGreaterThanOrEqual(1);
      expect(def.decisions.length).toBeLessThanOrEqual(3);
    });

    it('keeps decision contracts bounded and complete', () => {
      for (const spec of def.decisions) {
        // Allowed kinds: non-empty, unique, edit only on drafts.
        expect(spec.allowed.length).toBeGreaterThan(0);
        expect(new Set(spec.allowed).size).toBe(spec.allowed.length);
        if (spec.kind === 'tool') {
          expect(spec.allowed).not.toContain('edit');
          expect(spec.args.length).toBeGreaterThan(0);
          for (const arg of spec.args) {
            // Exactly one value channel: bounded literal or i18n key.
            expect(Boolean(arg.value) !== Boolean(arg.valueKey)).toBe(true);
          }
        } else {
          expect(spec.allowed).toContain('edit');
          expect(spec.to.endsWith('example.invalid')).toBe(true);
          expect(spec.outcome.edit).toBeTruthy();
        }
        expect(spec.outcome.confirm).toBeTruthy();
        expect(spec.outcome.cancel).toBeTruthy();
      }
    });

    it('contains no URL, path, command, secret or provider name', () => {
      for (const s of strings) {
        expect(s, `forbidden token in ${JSON.stringify(s)}`).not.toMatch(
          FORBIDDEN
        );
      }
    });

    it('keeps every email-like identifier on example.invalid', () => {
      const emails = strings.flatMap((s) => s.match(/[\w.+-]+@[\w.-]+/g) ?? []);
      for (const email of emails) {
        expect(email.endsWith('example.invalid')).toBe(true);
      }
    });

    it('uses only static HH:MM times — nothing clock-derived', () => {
      for (const s of strings) {
        expect(s).not.toMatch(/\d{4}-\d{2}-\d{2}T/);
      }
      const numbers: number[] = [];
      const walk = (v: unknown): void => {
        if (typeof v === 'number') numbers.push(v);
        else if (Array.isArray(v)) v.forEach(walk);
        else if (v !== null && typeof v === 'object')
          Object.values(v).forEach(walk);
      };
      walk(def);
      for (const n of numbers) {
        expect(n, 'epoch-like number found').toBeLessThan(100_000);
      }
    });

    it('references only i18n keys under the showroom namespace', () => {
      const keyFields = strings.filter((s) => s.startsWith('showroom.'));
      // Every definition is overwhelmingly i18n keys — a raw sentence here
      // would bypass the 6-locale contract.
      expect(keyFields.length).toBeGreaterThan(10);
      for (const key of keyFields) {
        expect(key).toMatch(/^showroom(\.[a-z0-9_]+)+$/);
      }
    });
  }
);

describe('the original mission keeps its P0 anchors', () => {
  const morning = getShowroomMission('overloaded_morning');

  it('still decides the email reply then the calendar move', () => {
    expect(morning.decisions.map((d) => d.id)).toEqual([
      'email_reply',
      'calendar_adjustment',
    ]);
    const email = morning.decisions[0];
    expect(email.kind === 'draft' && email.to).toBe(
      'emma@atlas.example.invalid'
    );
  });
});

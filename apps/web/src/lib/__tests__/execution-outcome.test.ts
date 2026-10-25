/**
 * What a tool step did, added up per label (owner request 2026-10-24) — the
 * same cases as the server's persisted trace (`test_trace_capture.py`), so the
 * live line and the reloaded one say the same thing.
 */
import { describe, expect, it } from 'vitest';

import {
  addToTally,
  newTally,
  outcomeCounts,
  outcomeText,
  settledLabel,
  summarizeTally,
} from '../execution-outcome';

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key;

describe('summarizeTally', () => {
  it('counts a call once by its key, its latest outcome kept', () => {
    const tally = newTally();
    addToTally(tally, 'call_0', undefined);
    addToTally(tally, 'call_0', { failed: 0, found: 12, shown: 5 });
    expect(summarizeTally(tally)).toEqual({ found: 12, shown: 5 });
  });

  it('says a tool was called twice and adds its calls up', () => {
    const tally = newTally();
    addToTally(tally, 'call_0', { failed: 0, found: 3, shown: 3 });
    addToTally(tally, 'call_1', { failed: 1 });
    expect(summarizeTally(tally)).toEqual({ calls: 2, found: 3, failed: 1 });
  });

  it('takes a pipeline total as it comes', () => {
    const tally = newTally();
    addToTally(tally, undefined, { calls: 3, found: 7, failed: 0 });
    expect(summarizeTally(tally)).toEqual({ calls: 3, found: 7 });
  });

  it('has nothing to say about a step that only ran', () => {
    const tally = newTally();
    addToTally(tally, 'call_0', { failed: 0 });
    expect(summarizeTally(tally)).toEqual({});
  });
});

describe('outcomeCounts', () => {
  it('keeps non-negative integers of known names only', () => {
    expect(outcomeCounts({ found: '12', shown: true, failed: -1, calls: 2, subject: 3 })).toEqual({
      calls: 2,
    });
    expect(outcomeCounts('12 emails')).toEqual({});
  });
});

describe('settledLabel', () => {
  it('drops the ellipsis that announced work in progress, and nothing else', () => {
    expect(settledLabel('Récupération des e-mails...')).toBe('Récupération des e-mails');
    expect(settledLabel('正在检索邮件…')).toBe('正在检索邮件');
    expect(settledLabel('Envoi en cours ...')).toBe('Envoi en cours');
    expect(settledLabel('Consulte les options de partage')).toBe('Consulte les options de partage');
    expect(settledLabel('v1.2... avant')).toBe('v1.2... avant');
  });
});

describe('outcomeText', () => {
  it('words the counts worth saying, joined', () => {
    expect(outcomeText(t, { calls: 2, found: 12, shown: 5, failed: 1 })).toBe(
      [
        'execution.outcome.calls:{"count":2}',
        'execution.outcome.found:{"count":12}',
        'execution.outcome.shown:{"count":5}',
        'execution.outcome.failed:{"count":1}',
      ].join('execution.outcome.joiner')
    );
    expect(outcomeText(t, {})).toBe('');
    expect(outcomeText(t, undefined)).toBe('');
  });
});

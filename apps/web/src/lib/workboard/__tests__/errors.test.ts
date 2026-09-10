/**
 * A failed run says WHY, in the reader's language (ADR-276).
 *
 * `last_run_error` carries a typed code and, sometimes, a bounded technical
 * message after it. The board used to print the whole string: a card showed
 * `workboard_assignee_inactive` — a machine identifier, in English, in all six
 * languages — where the backend's own contract says « the board resolves the
 * code from the frontend locales » (`core/i18n_workboard`).
 */
import { describe, expect, it } from 'vitest';

import { runFailure, workboardErrorKey } from '@/lib/workboard/errors';

/** The identity translator every test here reads: a key comes back as itself. */
const t = (key: string) => key;

describe('workboardErrorKey', () => {
  it('resolves a known refusal', () => {
    expect(workboardErrorKey('workboard_title_required')).toBe('workboard.errors.title_required');
  });

  it('falls back rather than showing a raw code', () => {
    expect(workboardErrorKey('workboard_unheard_of')).toBe('workboard.errors.generic');
    expect(workboardErrorKey(null)).toBe('workboard.errors.generic');
  });
});

describe('runFailure', () => {
  it('says nothing when the run left nothing', () => {
    expect(runFailure(t, null)).toBeNull();
    expect(runFailure(t, '   ')).toBeNull();
  });

  it('translates a bare code and carries no detail', () => {
    expect(runFailure(t, 'workboard_assignee_inactive')).toEqual({
      label: 'workboard.run_errors.assignee_inactive',
      detail: null,
    });
  });

  it('splits the code from the technical message it carries', () => {
    expect(runFailure(t, 'workboard_run_failed: TimeoutError: 600s')).toEqual({
      label: 'workboard.run_errors.run_failed',
      // The rest of the string, colons included: the evidence is not re-parsed.
      detail: 'TimeoutError: 600s',
    });
  });

  it('never shows a code it has not learnt', () => {
    const unknown = runFailure(t, 'workboard_from_the_future: nope');
    expect(unknown).toEqual({ label: 'workboard.run_errors.generic', detail: 'nope' });
  });

  it('treats a string that is not a code at all as the detail', () => {
    // Defensive: nothing writes this shape today, and a reader must still get
    // a sentence rather than a raw fragment as its heading.
    expect(runFailure(t, 'boom')).toEqual({
      label: 'workboard.run_errors.generic',
      detail: 'boom',
    });
  });
});

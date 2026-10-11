import { describe, expect, it } from 'vitest';
import { applicationCommandStatusSchema } from '../application-commands';

const id = '00000000-0000-4000-8000-000000000001';
const expires = '2026-12-01T10:00:00Z';
const base = { schema_version: 1, command_id: id, operation_id: 'preferences.update',
  phase: 'pending', expires_at: expires, interaction: null, outcome: null };

describe('current command receipt contract', () => {
  it('keeps a prior partial receipt separate from a resuming operation and its live actions', () => {
    const prior = { phase: 'waiting', success: false, committed: true, no_op: false,
      values: { font_size: 17 }, error_code: null,
      interaction: { interaction_id: id, kind: 'device', expires_at: expires } };
    const resuming = { ...base, phase: 'resuming', prior_outcome: prior };
    expect(applicationCommandStatusSchema.safeParse(resuming).success).toBe(true);
    expect(applicationCommandStatusSchema.safeParse({ ...resuming, interaction: prior.interaction }).success).toBe(false);
    expect(applicationCommandStatusSchema.safeParse({ ...base, prior_outcome: prior }).success).toBe(false);
  });

  it('never treats pending or claimed data as an execution receipt', () => {
    for (const phase of ['pending', 'claimed']) {
      expect(applicationCommandStatusSchema.safeParse({ ...base, phase,
        outcome: { phase, success: false, committed: false, no_op: false,
          values: {}, error_code: null, interaction: null } }).success).toBe(false);
    }
  });

  it('refuses foreign or deadline-shifted interactions rather than rendering live buttons', () => {
    const interaction = { interaction_id: id, kind: 'device', expires_at: expires };
    const outcome = { phase: 'waiting', success: false, committed: true, no_op: false,
      values: { font_size: 17 }, error_code: null, interaction };
    const valid = { ...base, phase: 'waiting', interaction, outcome };
    expect(applicationCommandStatusSchema.safeParse(valid).success).toBe(true);
    for (const change of [{ interaction_id: '00000000-0000-4000-8000-000000000002' }, { expires_at: '2026-12-02T10:00:00Z' }]) {
      const altered = { ...interaction, ...change };
      expect(applicationCommandStatusSchema.safeParse({ ...valid, interaction: altered, outcome: { ...outcome, interaction: altered } }).success).toBe(false);
    }
  });

  it('refuses private fields and non-boolean commitment claims', () => {
    expect(applicationCommandStatusSchema.safeParse({ ...base, origin_binding_encrypted: 'private' }).success).toBe(false);
    expect(applicationCommandStatusSchema.safeParse({ ...base, phase: 'committed', outcome: {
      phase: 'committed', success: true, committed: 'true', no_op: false, values: {}, error_code: null, interaction: null,
    } }).success).toBe(false);
  });
});

/**
 * Unit tests for the client-side password policy (mirrors the backend rules:
 * ≥10 chars, ≥2 uppercase, ≥2 digits, ≥2 special). The `t` stub echoes the i18n
 * key so assertions pin which rule failed without depending on translations.
 */
import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';

import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  getPasswordRequirementChecks,
  getPasswordRequirementsMessage,
  validatePassword,
} from '../password-validation';

const t = ((key: string, opts?: unknown): string =>
  opts && typeof opts === 'object'
    ? `${key} ${JSON.stringify(opts)}`
    : key) as unknown as TFunction;

/** True when at least one error string references the given i18n rule fragment. */
function hasError(errors: string[], fragment: string): boolean {
  return errors.some(e => e.includes(fragment));
}

describe('validatePassword', () => {
  it('accepts a policy-compliant password', () => {
    const result = validatePassword('AB12!@cdef', t);
    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it('flags a too-short password missing every class', () => {
    const result = validatePassword('abc', t);
    expect(result.isValid).toBe(false);
    expect(hasError(result.errors, 'min_length')).toBe(true);
    expect(hasError(result.errors, 'min_uppercase')).toBe(true);
    expect(hasError(result.errors, 'min_digits')).toBe(true);
    expect(hasError(result.errors, 'min_special')).toBe(true);
  });

  it('flags an over-long password (max_length branch)', () => {
    const result = validatePassword('A'.repeat(PASSWORD_MAX_LENGTH + 2), t);
    expect(result.isValid).toBe(false);
    expect(hasError(result.errors, 'max_length')).toBe(true);
    // all uppercase, so digits & special still fail
    expect(hasError(result.errors, 'min_digits')).toBe(true);
    expect(hasError(result.errors, 'min_special')).toBe(true);
  });

  it('flags only the missing special-char class (letters + no special)', () => {
    // 10 chars, but ZERO digits and ZERO special chars → only uppercase,
    // digits and special fail; length passes.
    const result = validatePassword('ABcdefghij', t);
    expect(result.isValid).toBe(false);
    expect(hasError(result.errors, 'min_length')).toBe(false);
    expect(hasError(result.errors, 'min_special')).toBe(true);
    expect(hasError(result.errors, 'min_digits')).toBe(true);
  });

  it('does NOT count digits as special characters (regression: unescaped "-" range)', () => {
    // Regression guard: `escapeRegExp` must escape "-", otherwise the "+-="
    // fragment of PASSWORD_SPECIAL_CHARS forms the regex range \+..= (0x2B..0x3D)
    // which spans the digits 0-9 — making ANY 2 digits satisfy min_special and
    // wrongly accepting a password with no real special character.
    const result = validatePassword('ABcdef1234', t);
    expect(result.isValid).toBe(false);
    expect(hasError(result.errors, 'min_special')).toBe(true);
  });

  it('accepts a password whose special requirement is met by real symbols', () => {
    const result = validatePassword('ABcdef12!@', t);
    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it('still counts genuine special characters that live inside the buggy range', () => {
    // ".", "/", ":", ";", "<", "=", "," and "-" are legitimately special AND
    // sit in 0x2B..0x3D — they must keep counting after the fix.
    const result = validatePassword('ABcdefgh.-', t);
    expect(hasError(result.errors, 'min_special')).toBe(false);
  });
});

describe('getPasswordRequirementsMessage', () => {
  it('interpolates the policy thresholds into the i18n message', () => {
    const msg = getPasswordRequirementsMessage(t);
    expect(msg).toContain('auth.password.requirements_message');
    expect(msg).toContain(`"minLength":${PASSWORD_MIN_LENGTH}`);
  });
});

describe('getPasswordRequirementChecks', () => {
  it('reports per-requirement met flags for a compliant password', () => {
    const checks = getPasswordRequirementChecks('AB12!@cdef', t);
    expect(checks).toHaveLength(4);
    expect(checks.every(c => c.met)).toBe(true);
  });

  it('reports the unmet requirement for a weak password', () => {
    const checks = getPasswordRequirementChecks('abcdefghij', t);
    const byLabel = Object.fromEntries(checks.map(c => [c.label.split(' ')[0], c.met]));
    expect(byLabel['auth.password.checks.min_length']).toBe(true); // 10 chars
    expect(byLabel['auth.password.checks.min_uppercase']).toBe(false);
    expect(byLabel['auth.password.checks.min_digits']).toBe(false);
    expect(byLabel['auth.password.checks.min_special']).toBe(false);
  });
});

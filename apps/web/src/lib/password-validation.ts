/**
 * Password validation utilities.
 *
 * Centralized password policy enforcement for non-OAuth accounts.
 * This module mirrors the backend validation rules.
 *
 * Password Policy:
 * - Minimum 10 characters
 * - At least 2 uppercase letters
 * - At least 2 special characters
 * - At least 2 digits
 *
 * Note: All public functions require a `t` (TFunction) parameter for i18n support.
 * These are pure utility functions that cannot use React hooks.
 */

import type { TFunction } from 'i18next';

// Password policy constants (must match backend constants.py)
export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_LENGTH = 128;
export const PASSWORD_MIN_UPPERCASE = 2;
export const PASSWORD_MIN_SPECIAL = 2;
export const PASSWORD_MIN_DIGITS = 2;
export const PASSWORD_SPECIAL_CHARS = '!@#$%^&*()_+-=[]{}|;\':",./<>?`~';

export interface PasswordValidationResult {
  isValid: boolean;
  errors: string[];
}

/**
 * Validate password against policy requirements.
 *
 * @param password - The password to validate
 * @param t - Translation function from react-i18next
 */
export function validatePassword(password: string, t: TFunction): PasswordValidationResult {
  const errors: string[] = [];

  // Check minimum length
  if (password.length < PASSWORD_MIN_LENGTH) {
    errors.push(t('auth.password.errors.min_length', { count: PASSWORD_MIN_LENGTH }));
  }

  // Check maximum length
  if (password.length > PASSWORD_MAX_LENGTH) {
    errors.push(t('auth.password.errors.max_length', { count: PASSWORD_MAX_LENGTH }));
  }

  // Count uppercase letters
  const uppercaseCount = (password.match(/[A-Z]/g) || []).length;
  if (uppercaseCount < PASSWORD_MIN_UPPERCASE) {
    errors.push(t('auth.password.errors.min_uppercase', { count: PASSWORD_MIN_UPPERCASE }));
  }

  // Count digits
  const digitCount = (password.match(/[0-9]/g) || []).length;
  if (digitCount < PASSWORD_MIN_DIGITS) {
    errors.push(t('auth.password.errors.min_digits', { count: PASSWORD_MIN_DIGITS }));
  }

  // Count special characters
  const specialRegex = new RegExp(`[${escapeRegExp(PASSWORD_SPECIAL_CHARS)}]`, 'g');
  const specialCount = (password.match(specialRegex) || []).length;
  if (specialCount < PASSWORD_MIN_SPECIAL) {
    errors.push(t('auth.password.errors.min_special', { count: PASSWORD_MIN_SPECIAL }));
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Get a human-readable message describing password requirements.
 *
 * @param t - Translation function from react-i18next
 */
export function getPasswordRequirementsMessage(t: TFunction): string {
  return t('auth.password.requirements_message', {
    minLength: PASSWORD_MIN_LENGTH,
    minUppercase: PASSWORD_MIN_UPPERCASE,
    minDigits: PASSWORD_MIN_DIGITS,
    minSpecial: PASSWORD_MIN_SPECIAL,
  });
}

/**
 * Get individual requirement checks for UI display.
 *
 * @param password - The password to check
 * @param t - Translation function from react-i18next
 */
export function getPasswordRequirementChecks(
  password: string,
  t: TFunction
): {
  label: string;
  met: boolean;
}[] {
  const uppercaseCount = (password.match(/[A-Z]/g) || []).length;
  const digitCount = (password.match(/[0-9]/g) || []).length;
  const specialRegex = new RegExp(`[${escapeRegExp(PASSWORD_SPECIAL_CHARS)}]`, 'g');
  const specialCount = (password.match(specialRegex) || []).length;

  return [
    {
      label: t('auth.password.checks.min_length', { count: PASSWORD_MIN_LENGTH }),
      met: password.length >= PASSWORD_MIN_LENGTH,
    },
    {
      label: t('auth.password.checks.min_uppercase', { count: PASSWORD_MIN_UPPERCASE }),
      met: uppercaseCount >= PASSWORD_MIN_UPPERCASE,
    },
    {
      label: t('auth.password.checks.min_digits', { count: PASSWORD_MIN_DIGITS }),
      met: digitCount >= PASSWORD_MIN_DIGITS,
    },
    {
      label: t('auth.password.checks.min_special', { count: PASSWORD_MIN_SPECIAL }),
      met: specialCount >= PASSWORD_MIN_SPECIAL,
    },
  ];
}

/**
 * Escape special regex characters.
 */
function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

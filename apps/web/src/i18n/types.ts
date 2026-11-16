/** The text-only translation contract shared by presentation helpers. */

import type { TOptions } from 'i18next';

/** Object and detailed results belong to callers using the full TFunction. */
export type TextTranslationOptions = TOptions & {
  defaultValue?: string;
  returnObjects?: false;
  returnDetails?: false;
  returnNull?: false;
};

/**
 * Accept the same two text calls as i18next: a key alone, or a key and options.
 * An optional second parameter would also promise `t(key, undefined)`, which
 * the library does not accept. Keep its option types without requiring its
 * branded function on small helpers and their test doubles.
 */
export interface TextTranslator {
  (key: string): string;
  (key: string, options: TextTranslationOptions): string;
}

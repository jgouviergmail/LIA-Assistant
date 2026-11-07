/**
 * What the memory form holds a text to, ahead of the API.
 *
 * The API refuses a memory's text past the bounds it publishes on the list
 * (`MemoryLimits`). The form states them first, so that a refusal is a sentence
 * under the field and never a failed save with no reason given.
 *
 * It counts what the API counts: one character per code point. `String.length`
 * counts UTF-16 units, an emoji twice, and would block a text the API accepts.
 *
 * @module memories/text-bounds
 */

import type { MemoryLimits } from '@/hooks/useMemories';

const MEMORY_TEXT_FIELDS = ['content', 'trigger_topic', 'usage_nuance'] as const;

export type MemoryTextField = (typeof MEMORY_TEXT_FIELDS)[number];

/** The shortest and longest text a field accepts, in characters. */
export interface TextBound {
  min: number;
  max: number;
}

/** A text's length as the API measures it. */
export function countCharacters(text: string): number {
  return [...text].length;
}

/** Each text field's bound, read from what the API published. */
export function memoryTextBounds(limits: MemoryLimits): Record<MemoryTextField, TextBound> {
  return {
    content: { min: limits.content_min_chars, max: limits.content_max_chars },
    trigger_topic: { min: 0, max: limits.trigger_topic_max_chars },
    usage_nuance: { min: 0, max: limits.usage_nuance_max_chars },
  };
}

/** How many characters a text runs past its ceiling, 0 when it fits. */
export function excessCharacters(text: string, bound: TextBound): number {
  return Math.max(0, countCharacters(text) - bound.max);
}

/** Whether a text stops short of its floor. An empty field has nothing to refuse yet. */
export function isTooShort(text: string, bound: TextBound): boolean {
  const count = countCharacters(text);
  return count > 0 && count < bound.min;
}

/**
 * Whether the API refused what was sent, the one failure the person can act on.
 *
 * The form states the bounds first, so this is what a form that could not read them
 * still gets to name: the list failed, or a tab outlived a lowered bound.
 */
export function isRefusedInput(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'status' in error && error.status === 422;
}

/**
 * Whether the form may submit these texts.
 *
 * With the limits still unknown, only an empty content is held back: the API decides,
 * as it always does.
 */
export function isMemoryTextSavable(
  texts: Record<MemoryTextField, string>,
  limits: MemoryLimits | undefined
): boolean {
  if (!texts.content.trim()) return false;
  if (!limits) return true;
  const bounds = memoryTextBounds(limits);
  return MEMORY_TEXT_FIELDS.every(
    field =>
      excessCharacters(texts[field], bounds[field]) === 0 &&
      !isTooShort(texts[field], bounds[field])
  );
}

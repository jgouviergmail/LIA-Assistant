/**
 * The doc text must not become a second authority on the ladder (ADR-245).
 *
 * It was one: every entry enumerated the accepted values, and by the time the
 * ladder moved into the payload the strings still described "off" toggles and
 * "-1 = auto" sentinels for models that had neither. The dropdown right above
 * the text is the authority; this file may only add what the dropdown cannot
 * say.
 */
import { describe, expect, it } from 'vitest';

import { REASONING_LEVELS } from '@/types/llm-config';
import { REASONING_DOC_TEXT } from '../reasoningDocText';

describe('reasoning doc text', () => {
  it('never enumerates a ladder', () => {
    // Two or more level names separated by "/" is the enumeration shape the
    // old entries used ("low / medium / high", "off / high / max").
    const names = REASONING_LEVELS.filter(l => l !== 'provider_default').join('|');
    const enumeration = new RegExp(`\b(?:${names}|off|auto)\b\s*/\s*\b`, 'i');
    const offenders = Object.entries(REASONING_DOC_TEXT).filter(([, text]) =>
      enumeration.test(text)
    );
    expect(offenders).toEqual([]);
  });

  it('never mentions the dropped sentinels', () => {
    const offenders = Object.entries(REASONING_DOC_TEXT).filter(([, text]) =>
      /-1\s*=|0\s*=\s*off|toggle on/i.test(text)
    );
    expect(offenders).toEqual([]);
  });

  it('says something for every entry', () => {
    for (const [key, text] of Object.entries(REASONING_DOC_TEXT)) {
      expect(text.length, key).toBeGreaterThan(20);
    }
  });
});

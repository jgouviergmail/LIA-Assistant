/**
 * One sentence for what a batch left untouched (ADR-259): the count and every
 * distinct reason, localized under the caller's key prefix — shared by the
 * documents and the templates.
 */

import { describe, expect, it, vi } from 'vitest';

import { skippedSentence } from '../batch-report';

describe('skippedSentence', () => {
  it('names each distinct reason once, in first-seen order, under the prefix', () => {
    const t = vi.fn((key: string, options?: Record<string, unknown>) =>
      options && 'reasons' in options ? `${key}|${options.count}|${options.reasons}` : key
    );
    const sentence = skippedSentence(t, 'spaces.documents', [
      { code: 'document_busy' },
      { code: 'same_space' },
      { code: 'document_busy' },
    ]);
    expect(sentence).toBe(
      'spaces.documents.skipped|3|spaces.documents.skip.document_busy, spaces.documents.skip.same_space'
    );
    expect(t).toHaveBeenCalledWith('spaces.documents.skip.document_busy', {
      defaultValue: 'document_busy',
    });
  });
});

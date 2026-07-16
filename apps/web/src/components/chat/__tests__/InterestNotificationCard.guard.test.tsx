/**
 * isInterestNotificationMetadata — the SSE-metadata type guard.
 */

import { describe, it, expect } from 'vitest';

import { isInterestNotificationMetadata } from '../InterestNotificationCard';

describe('isInterestNotificationMetadata', () => {
  it('accepts a well-formed proactive-interest metadata object', () => {
    expect(
      isInterestNotificationMetadata({
        type: 'proactive_interest',
        target_id: 'abc',
        feedback_enabled: true,
      })
    ).toBe(true);
  });

  it.each([
    ['null', null],
    ['a string', 'proactive_interest'],
    ['wrong type', { type: 'other', target_id: 'abc', feedback_enabled: true }],
    ['empty target_id', { type: 'proactive_interest', target_id: '', feedback_enabled: true }],
    ['missing feedback flag', { type: 'proactive_interest', target_id: 'abc' }],
    ['non-boolean flag', { type: 'proactive_interest', target_id: 'abc', feedback_enabled: 'yes' }],
  ])('rejects %s', (_label, value) => {
    expect(isInterestNotificationMetadata(value)).toBe(false);
  });
});

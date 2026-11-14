/**
 * A jump to a message of ANOTHER discussion, carried across the switch.
 *
 * Each discussion mounts its own chat view: the search that found the message
 * is gone once the discussion it opens is on screen. The jump waits here, is
 * taken by the view it names and by no other, once, and never long after.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { DISCUSSION_JUMP_TTL_MS } from '@/lib/constants';
import {
  resetDiscussionJumpForTests,
  requestDiscussionJump,
  takeDiscussionJump,
} from '@/lib/discussion-jump';

const JUMP = { conversationId: 'annex-1', createdAt: '2026-11-02T08:03:00.000Z', term: 'devis' };

describe('the jump to another discussion', () => {
  beforeEach(() => resetDiscussionJumpForTests());

  it('is taken by the discussion it names, once', () => {
    requestDiscussionJump(JUMP, 1_000);

    expect(takeDiscussionJump('annex-1', 1_500)).toEqual(JUMP);
    expect(takeDiscussionJump('annex-1', 1_600)).toBeNull();
  });

  it('is left alone by another discussion that opens meanwhile', () => {
    requestDiscussionJump(JUMP, 1_000);

    expect(takeDiscussionJump('main', 1_200)).toBeNull();
    expect(takeDiscussionJump('annex-1', 1_300)).toEqual(JUMP);
  });

  it('is never replayed once it is stale', () => {
    requestDiscussionJump(JUMP, 1_000);

    expect(takeDiscussionJump('annex-1', 1_000 + DISCUSSION_JUMP_TTL_MS + 1)).toBeNull();
    // Taken stale, it is gone for good.
    expect(takeDiscussionJump('annex-1', 1_000)).toBeNull();
  });

  it('is replaced by the next one asked', () => {
    requestDiscussionJump(JUMP, 1_000);
    requestDiscussionJump({ ...JUMP, conversationId: 'annex-2' }, 1_100);

    expect(takeDiscussionJump('annex-1', 1_200)).toBeNull();
    expect(takeDiscussionJump('annex-2', 1_200)?.conversationId).toBe('annex-2');
  });
});

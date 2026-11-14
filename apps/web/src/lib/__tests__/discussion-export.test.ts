import { describe, expect, it } from 'vitest';

import { apiEndpointUrl } from '@/lib/api-client';
import { discussionExportUrl } from '@/lib/discussion-export';
import type { ConversationSummary } from '@/types/conversation';

function discussion(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: '00000000-0000-4000-8000-00000000c002',
    user_id: 'owner',
    kind: 'secondary',
    revision: 7,
    title: 'Travel & food',
    message_count: 3,
    total_tokens: 0,
    created_at: '',
    updated_at: '',
    ...overrides,
  };
}

describe('the download address of one discussion', () => {
  it('names an annex by its identity and the generation the person is looking at', () => {
    const url = new URL(discussionExportUrl(discussion()), 'https://lia.example');

    expect(url.pathname.endsWith('/conversations/me/export')).toBe(true);
    expect(url.searchParams.get('conversation_id')).toBe('00000000-0000-4000-8000-00000000c002');
    expect(url.searchParams.get('conversation_revision')).toBe('7');
  });

  it.each([null, discussion({ kind: 'main', revision: 3 })])(
    'asks for Main with no selection, whatever the list holds of it (%#)',
    main => {
      // The server resolves Main's current generation itself: a revision read
      // from an older page would refuse a document that exists.
      expect(discussionExportUrl(main)).toBe(apiEndpointUrl('/conversations/me/export'));
    }
  );

  it('goes through the API origin, never a path relative to the page', () => {
    // A relative URL only works behind a reverse proxy that re-routes /api/v1.
    expect(discussionExportUrl(null)).toBe(apiEndpointUrl('/conversations/me/export'));
    expect(discussionExportUrl(discussion())).toContain(
      apiEndpointUrl('/conversations/me/export')
    );
  });
});

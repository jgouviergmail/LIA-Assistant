import { describe, expect, it } from 'vitest';
import { meetingListPage, meetingListQuery, meetingListSearch } from '../list-location';

describe('meeting list location', () => {
  it('bounds untrusted URL input and preserves literal search characters', () => {
    expect(meetingListPage('0')).toBe(1);
    expect(meetingListPage('100001')).toBe(1);
    expect(meetingListQuery(' x\0y ')).toBe('xy');
    expect(meetingListQuery('z'.repeat(300))).toHaveLength(200);
    const params = new URLSearchParams(meetingListSearch(3, 'Café & 100%_\\'));
    expect(params.get('page')).toBe('3');
    expect(params.get('q')).toBe('Café & 100%_\\');
    expect(meetingListSearch(1, '')).toBe('');
  });
});

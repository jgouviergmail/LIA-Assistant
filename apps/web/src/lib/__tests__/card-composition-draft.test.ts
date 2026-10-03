import { describe, expect, it } from 'vitest';
import { encodeCompositionDraft, decodeCompositionDraft } from '../card-composition-draft';
import type { CardCompositionDraft } from '@/types/card-actions';

const draft: CardCompositionDraft = {
  text: 'My edited reply',
  label: 'Subject',
  selection: {
    version: 1,
    message_id: '00000000-0000-0000-0000-000000000003',
    run_id: 'run-a',
    registry_id: 'email_a',
    action: 'reply',
  },
};
describe('atomic per-user composition draft storage', () => {
  it('preserves legacy plain drafts including ordinary JSON prose', () => {
    expect(decodeCompositionDraft('{"text":"A draft"}')).toEqual({ text: '{"text":"A draft"}' });
    expect(encodeCompositionDraft('Plain draft')).toBe('Plain draft');
  });
  it('round trips text and selection together, with no technical ID in visible text', () => {
    const stored = encodeCompositionDraft(draft.text, draft);
    expect(decodeCompositionDraft(stored)).toEqual({ text: draft.text, composition: draft });
    expect(decodeCompositionDraft(stored).text).not.toContain(draft.selection.message_id);
  });
  it('refuses malformed or unknown versioned selections', () => {
    const stored = encodeCompositionDraft(draft.text, draft);
    expect(decodeCompositionDraft(stored.replace('"version":1', '"version":2'))).toEqual({});
    expect(decodeCompositionDraft(stored.slice(0, -1))).toEqual({});
  });
  it('preserves the backend limit of 200 Unicode characters in an emoji subject', () => {
    const unicode = { ...draft, label: '🚀'.repeat(200) };
    expect(decodeCompositionDraft(encodeCompositionDraft(unicode.text, unicode))).toEqual({
      text: unicode.text,
      composition: unicode,
    });
  });
});

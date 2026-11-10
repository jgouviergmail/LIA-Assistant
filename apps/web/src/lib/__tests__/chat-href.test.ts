/** URL encoding and one-shot intent identity stay identical across every consumer. */
import { describe, expect, it } from 'vitest';
import { chatIntentHref } from '../chat-href';

describe('chatIntentHref', () => {
  it('keeps the historical intent encoding when no capability is invoked', () => {
    // Every briefing card builds its link this way, so the intent encoding
    // must stay byte-identical (%20, never the + of URLSearchParams). The
    // one-shot `iid` (ADR-210) is appended AFTER the intent, so the historical
    // prefix survives verbatim.
    expect(chatIntentHref('fr', 'Résume mes mails')).toMatch(
      /^\/fr\/dashboard\/chat\?intent=R%C3%A9sume%20mes%20mails&iid=/
    );
  });

  it('carries a one-shot id, fresh on EVERY call (ADR-210)', () => {
    // One click builds one href: a replay of that href (omnibox, session
    // restore, router cache) is detectable because its iid was consumed.
    // Two CLICKS on the same action stay two executions: different iids.
    const first = new URLSearchParams(chatIntentHref('fr', 'go').split('?')[1]);
    const second = new URLSearchParams(chatIntentHref('fr', 'go').split('?')[1]);

    expect(first.get('iid')).toBeTruthy();
    expect(second.get('iid')).toBeTruthy();
    expect(first.get('iid')).not.toBe(second.get('iid'));
  });

  it('carries the capability and its subject (ADR-191) alongside the iid', () => {
    const href = chatIntentHref('fr', 'Point 360° sur Paul Martin', {
      capability: 'person_overview',
      subject: 'Paul Martin',
    });
    const query = new URLSearchParams(href.split('?')[1]);

    expect(query.get('intent')).toBe('Point 360° sur Paul Martin');
    expect(query.get('capability')).toBe('person_overview');
    expect(query.get('subject')).toBe('Paul Martin');
    expect(query.get('iid')).toBeTruthy();
  });

  it('survives a name the URL would otherwise mangle', () => {
    const href = chatIntentHref('de', 'Punkt', {
      capability: 'person_overview',
      subject: 'Anaïs Müller & Co',
    });

    expect(new URLSearchParams(href.split('?')[1]).get('subject')).toBe('Anaïs Müller & Co');
  });
});

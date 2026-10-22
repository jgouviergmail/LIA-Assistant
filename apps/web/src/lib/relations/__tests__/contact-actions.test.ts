/**
 * The address book's own actions on a relationship (owner request 2026-10-21).
 *
 * Read through the REAL locale files: the wording is the owner's, and a key
 * that drifted or an interpolation that escaped an apostrophe would only show
 * in the composer of a real reader.
 */

import { describe, expect, it } from 'vitest';
import { createInstance } from 'i18next';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import type { ContactCard } from '@/hooks/useRelations';
import { contactQuickActions } from '../contact-actions';

const language = createInstance();
await language.init({
  lng: 'fr',
  resources: { fr: { translation: fr }, en: { translation: en } },
  // As the application configures it: React escapes, i18next must not.
  interpolation: { escapeValue: false },
});

function card(over: Partial<ContactCard> = {}): ContactCard {
  return {
    display_name: 'Marie Client',
    nickname: null,
    organization: null,
    occupation: null,
    birthday: null,
    biography: null,
    emails: [],
    phones: [],
    addresses: [],
    relations: [],
    links: [],
    important_dates: [],
    messaging: [],
    ...over,
  };
}

describe('contactQuickActions', () => {
  it('offers one action per email, address and number, each prefilling the owner’s request', () => {
    const columns = contactQuickActions(
      card({
        emails: [
          { value: 'marie@client.example', label: 'home' },
          { value: 'marie@atelier.example', label: 'work' },
        ],
        addresses: [{ value: "12 rue de l'Église\n75001 Paris", label: 'home' }],
        phones: [{ value: '+33 6 00 00 00 00', label: 'mobile' }],
      }),
      language.getFixedT('fr'),
      { telephony: true }
    );

    // One column per kind, in the card's order (owner request 2026-10-21).
    expect(columns.map(column => column.kind)).toEqual(['email', 'route', 'call']);
    const actions = columns.flatMap(column => column.actions);
    expect(actions.map(action => action.label)).toEqual([
      'Email marie@client.example',
      'Email marie@atelier.example',
      "Itinéraire vers 12 rue de l'Église 75001 Paris",
      'Appel LIA +33 6 00 00 00 00',
    ]);
    // The subject and the purpose are the person's to add: the request stops
    // where they type, and nothing is sent until they do.
    expect(actions.map(action => action.draft)).toEqual([
      'Envoie un email à marie@client.example au sujet de ',
      'Envoie un email à marie@atelier.example au sujet de ',
      "Recherche l'itinéraire pour aller à 12 rue de l'Église 75001 Paris",
      'Appelle le +33 6 00 00 00 00 pour ',
    ]);
    expect(new Set(actions.map(action => action.key)).size).toBe(actions.length);
  });

  it('offers a value stored twice once, and a blank one never', () => {
    const columns = contactQuickActions(
      card({
        emails: [
          { value: 'marie@client.example', label: 'home' },
          { value: ' marie@client.example ', label: 'work' },
          { value: '   ', label: null },
        ],
      }),
      language.getFixedT('fr'),
      { telephony: true }
    );

    expect(columns.flatMap(column => column.actions).map(action => action.label)).toEqual([
      'Email marie@client.example',
    ]);
  });

  it('speaks the reader’s language, and opens no column for a kind the card lacks', () => {
    const columns = contactQuickActions(
      card({ phones: [{ value: '+44 20 0000 0000', label: null }] }),
      language.getFixedT('en'),
      { telephony: true }
    );

    expect(columns.map(column => column.kind)).toEqual(['call']);
    const [action] = columns[0].actions;
    expect(action.label).toBe('LIA call +44 20 0000 0000');
    expect(action.draft).toBe('Call +44 20 0000 0000 to ');
  });

  it('offers no call without an active telephony connector', () => {
    // Owner request 2026-10-21: « Appel LIA » only when the telephony
    // connector is active — a call nothing can place is never offered.
    const columns = contactQuickActions(
      card({
        emails: [{ value: 'marie@client.example', label: null }],
        phones: [{ value: '+33 6 00 00 00 00', label: null }],
      }),
      language.getFixedT('fr'),
      { telephony: false }
    );

    expect(columns.map(column => column.kind)).toEqual(['email']);
  });

  it('offers nothing when no contact card was read', () => {
    expect(contactQuickActions(null, language.getFixedT('fr'), { telephony: true })).toEqual([]);
  });
});

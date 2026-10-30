/**
 * The address book's own actions on a relationship (owner requests 2026-10-21
 * and 2026-10-29).
 *
 * Read through the REAL locale files: the wording is the owner's, and a key
 * that drifted or an interpolation that escaped an apostrophe would only show
 * in the composer of a real reader.
 */

import { describe, expect, it } from 'vitest';
import { createInstance } from 'i18next';

import de from '../../../../locales/de/translation.json';
import en from '../../../../locales/en/translation.json';
import es from '../../../../locales/es/translation.json';
import fr from '../../../../locales/fr/translation.json';
import it_ from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';
import type { ContactCard } from '@/hooks/useRelations';
import { contactActionGroups } from '../contact-actions';

const RESOURCES = { de, en, es, fr, it: it_, zh };

const language = createInstance();
await language.init({
  lng: 'fr',
  resources: Object.fromEntries(
    Object.entries(RESOURCES).map(([lng, translation]) => [lng, { translation }])
  ),
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

/** One value of each kind, so every entry exists. */
const FULL = card({
  emails: [
    { value: 'marie@client.example', label: 'home' },
    { value: 'marie@atelier.example', label: 'work' },
  ],
  addresses: [{ value: "12 rue de l'Église\n75001 Paris", label: 'home' }],
  phones: [{ value: '+33 6 00 00 00 00', label: 'mobile' }],
});

describe('contactActionGroups', () => {
  it('offers one entry per kind, labelled by a short verb, its values as targets', () => {
    const groups = contactActionGroups(FULL, language.getFixedT('fr'), { telephony: true });

    // In the card's order (owner request 2026-10-21).
    expect(groups.map(group => group.kind)).toEqual(['email', 'route', 'call']);
    // The label never carries the value (owner request 2026-10-29): it is what
    // made every relationship lay its buttons out differently.
    expect(groups.map(group => group.label)).toEqual(['E-mail', 'Itinéraire', 'Appeler']);
    expect(groups.map(group => group.targets.map(target => target.value))).toEqual([
      ['marie@client.example', 'marie@atelier.example'],
      ["12 rue de l'Église 75001 Paris"],
      ['+33 6 00 00 00 00'],
    ]);
    // The subject and the purpose are the person's to add: the request stops
    // where they type, and nothing is sent until they do.
    expect(groups.flatMap(group => group.targets.map(target => target.draft))).toEqual([
      'Envoie un email à marie@client.example au sujet de ',
      'Envoie un email à marie@atelier.example au sujet de ',
      "Recherche l'itinéraire pour aller à 12 rue de l'Église 75001 Paris",
      'Appelle le +33 6 00 00 00 00 pour ',
    ]);
    const keys = groups.flatMap(group => group.targets.map(target => target.key));
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('carries the address book’s labels in the reader’s language, its own words otherwise', () => {
    const groups = contactActionGroups(
      card({
        emails: [
          { value: 'marie@client.example', label: 'home' },
          { value: 'marie@atelier.example', label: 'Maison de campagne' },
          { value: 'marie@perso.example', label: null },
        ],
      }),
      language.getFixedT('fr'),
      { telephony: true }
    );

    expect(groups[0].targets.map(target => target.tags)).toEqual([
      ['domicile'],
      ['Maison de campagne'],
      [],
    ]);
  });

  it('offers a value stored twice once, with both its labels, and a blank one never', () => {
    const groups = contactActionGroups(
      card({
        emails: [
          { value: 'marie@client.example', label: 'home' },
          { value: ' marie@client.example ', label: 'work' },
          { value: 'marie@client.example', label: 'home' },
          { value: '   ', label: null },
        ],
      }),
      language.getFixedT('fr'),
      { telephony: true }
    );

    expect(groups[0].targets).toHaveLength(1);
    expect(groups[0].targets[0].value).toBe('marie@client.example');
    expect(groups[0].targets[0].tags).toEqual(['domicile', 'travail']);
  });

  it.each(Object.keys(RESOURCES))('labels every entry without its value @ %s', lng => {
    const groups = contactActionGroups(FULL, language.getFixedT(lng), { telephony: true });

    for (const group of groups) {
      expect(group.label.trim()).not.toBe('');
      expect(group.label).not.toMatch(/\{\{|\}\}/);
      for (const target of group.targets) expect(group.label).not.toContain(target.value);
    }
  });

  it('speaks the reader’s language, and opens no entry for a kind the card lacks', () => {
    const groups = contactActionGroups(
      card({ phones: [{ value: '+44 20 0000 0000', label: null }] }),
      language.getFixedT('en'),
      { telephony: true }
    );

    expect(groups.map(group => group.kind)).toEqual(['call']);
    expect(groups[0].label).toBe('Call');
    expect(groups[0].targets[0].draft).toBe('Call +44 20 0000 0000 to ');
  });

  it('offers no call without an active telephony connector', () => {
    // Owner request 2026-10-21: a call only when the telephony connector is
    // active — a call nothing can place is never offered.
    const groups = contactActionGroups(FULL, language.getFixedT('fr'), { telephony: false });

    expect(groups.map(group => group.kind)).toEqual(['email', 'route']);
  });

  it('offers nothing when no contact card was read', () => {
    expect(contactActionGroups(null, language.getFixedT('fr'), { telephony: true })).toEqual([]);
  });
});

/**
 * The contact card — everything the address book holds, and nothing invented.
 *
 * The reader asked for ALL of a peer's contact details (addresses, relations,
 * "and all the rest"), so the oracles here are about completeness and honesty:
 *
 * - every block the provider stored reaches the screen;
 * - a block the provider does NOT store renders nothing — never a placeholder,
 *   which would read as "the address book holds nothing" (ADR-184);
 * - a birthday without a year keeps that year missing;
 * - a provider label we know is translated, one we do not is shown as typed.
 *
 * This file overrides the global i18n stub with one that honours
 * `defaultValue`, exactly as i18next does for a missing key — the fallback is
 * half the label contract and the key-echoing stub cannot express it.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { ContactCard } from '@/hooks/useRelations';

import { ContactCardBody } from '../ContactCardBody';

const { KNOWN } = vi.hoisted(() => ({
  KNOWN: {
    'relations.contact_label.home': 'domicile',
    'relations.contact_label.spouse': 'conjoint·e',
    'relations.contact_label.birthday': 'anniversaire',
    'relations.contact_nickname': 'Aussi appelé·e Gégé',
  } as Record<string, string>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) =>
      KNOWN[key] ?? options?.defaultValue ?? key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

function card(over: Partial<ContactCard> = {}): ContactCard {
  return {
    display_name: 'Gérard Dupont',
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

describe('ContactCardBody', () => {
  it('renders every block the address book holds', () => {
    renderWithProviders(
      <ContactCardBody
        locale="fr"
        card={card({
          nickname: 'Gégé',
          organization: 'ACME',
          occupation: 'Architecte',
          biography: 'Rencontré au forum.',
          birthday: '1978-04-07',
          emails: [{ value: 'gerard@example.com', label: 'home' }],
          phones: [{ value: '+33600000000', label: 'mobile' }],
          addresses: [{ value: '12 rue des Lilas, Lyon', label: 'home' }],
          relations: [{ value: 'Claire Lefèvre', label: 'spouse' }],
          links: [{ value: 'https://example.com', label: 'blog' }],
          important_dates: [{ value: '2011-09-03', label: 'anniversary' }],
          messaging: [{ value: 'gerard.d', label: 'skype' }],
        })}
      />
    );

    expect(screen.getByText('Aussi appelé·e Gégé')).toBeInTheDocument();
    expect(screen.getByText('Architecte · ACME')).toBeInTheDocument();
    expect(screen.getByText('gerard@example.com')).toBeInTheDocument();
    expect(screen.getByText('+33600000000')).toBeInTheDocument();
    expect(screen.getByText('12 rue des Lilas, Lyon')).toBeInTheDocument();
    expect(screen.getByText('Claire Lefèvre')).toBeInTheDocument();
    expect(screen.getByText('https://example.com')).toBeInTheDocument();
    expect(screen.getByText('gerard.d')).toBeInTheDocument();
    expect(screen.getByText('Rencontré au forum.')).toBeInTheDocument();
  });

  it('translates the provider labels it knows and keeps the ones it does not', () => {
    // An address book holds custom labels. Inventing a translation for
    // "Maison de campagne" is impossible; dropping it loses information.
    renderWithProviders(
      <ContactCardBody
        locale="fr"
        card={card({
          addresses: [
            { value: '12 rue des Lilas', label: 'home' },
            { value: '3 chemin du Puits', label: 'Maison de campagne' },
          ],
        })}
      />
    );
    expect(screen.getByText('domicile')).toBeInTheDocument();
    expect(screen.getByText('Maison de campagne')).toBeInTheDocument();
  });

  it('shows a birthday without a year without inventing one', () => {
    renderWithProviders(<ContactCardBody locale="fr" card={card({ birthday: '--04-07' })} />);
    const label = screen.getByText(/avril/);
    expect(label.textContent).toBe('7 avril');
  });

  it('localizes a full birthday, year included', () => {
    renderWithProviders(<ContactCardBody locale="fr" card={card({ birthday: '1978-04-07' })} />);
    expect(screen.getByText('7 avril 1978')).toBeInTheDocument();
  });

  it('passes through a birthday the provider stored as free text', () => {
    renderWithProviders(<ContactCardBody locale="fr" card={card({ birthday: 'au printemps' })} />);
    expect(screen.getByText('au printemps')).toBeInTheDocument();
  });

  it('opens a link safely, and only an http(s) one', () => {
    renderWithProviders(
      <ContactCardBody
        locale="fr"
        card={card({
          links: [
            { value: 'https://example.com', label: null },
            // The scheme is the point of the test: an address book is written
            // by a third party, and this app renders what it finds there.
            { value: 'javascript:alert(1)', label: null },
          ],
        })}
      />
    );
    const link = screen.getByRole('link', { name: 'https://example.com' });
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    // Rendered as text, never as an anchor: the value comes from a third
    // party's address book, which nobody in this app controls.
    expect(screen.getByText('javascript:alert(1)').tagName).toBe('SPAN');
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('renders nothing for a block the provider does not store', () => {
    // Apple and Microsoft have no relations, links, dates or messaging at all.
    // A "none" line here would state a negative nobody verified.
    const { container } = renderWithProviders(
      <ContactCardBody
        locale="fr"
        card={card({ emails: [{ value: 'gerard@example.com', label: null }] })}
      />
    );
    expect(screen.getByText('gerard@example.com')).toBeInTheDocument();
    expect(screen.queryByText('relations.contact_no_details')).not.toBeInTheDocument();
    expect(container.querySelectorAll('p')).toHaveLength(1);
  });

  it('says so when the address book holds nothing but a name', () => {
    renderWithProviders(<ContactCardBody locale="fr" card={card()} />);
    expect(screen.getByText('relations.contact_no_details')).toBeInTheDocument();
  });

  it('keeps two values that share a label, in the provider order', () => {
    // The same value can appear twice under two labels: keying on the value
    // alone would silently drop one of them.
    renderWithProviders(
      <ContactCardBody
        locale="fr"
        card={card({
          phones: [
            { value: '+33600000000', label: 'home' },
            { value: '+33600000000', label: 'work' },
          ],
        })}
      />
    );
    expect(screen.getAllByText('+33600000000')).toHaveLength(2);
  });
});

/**
 * The two lists a visitor reads before opening the live demonstrator.
 *
 * What must hold: every capability lands in exactly one column, under the
 * locale's own label for it; the columns are sorted so a reader can scan
 * them; and "the instance did not answer" is a sentence, never an empty
 * column.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

const LABELS: Record<string, string> = {
  'capabilities.items.web_search': 'Recherche web',
  'capabilities.items.meetings': 'Enregistrement de réunions',
  'capabilities.items.bookmarks': 'Bookmarks',
  'capabilities.items.attachments': 'Téléversement de fichiers',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => LABELS[key] ?? key }),
}));

import { DemoCapabilityLists, splitCapabilities } from '@/components/showroom/DemoCapabilityLists';
import type { PublicCapabilities } from '@/lib/demo-capabilities';

const CAPABILITIES: PublicCapabilities = {
  web_search: { enabled: true, family: 'reach' },
  meetings: { enabled: false, family: 'media' },
  bookmarks: { enabled: true, family: 'knowledge' },
  attachments: { enabled: false, family: 'media' },
};

describe('splitCapabilities', () => {
  it('puts every capability in exactly one column, labelled and sorted', () => {
    const { enabled, disabled } = splitCapabilities(CAPABILITIES, key => LABELS[key] ?? key);
    expect(enabled.map(item => item.label)).toEqual(['Bookmarks', 'Recherche web']);
    expect(disabled.map(item => item.label)).toEqual([
      'Enregistrement de réunions',
      'Téléversement de fichiers',
    ]);
    expect(enabled.length + disabled.length).toBe(Object.keys(CAPABILITIES).length);
  });

  it('names a capability the locale does not know by its key, never drops it', () => {
    const { enabled } = splitCapabilities(
      { brand_new: { enabled: true, family: 'x' } },
      key => key
    );
    expect(enabled).toEqual([{ key: 'brand_new', label: 'capabilities.items.brand_new' }]);
  });
});

describe('DemoCapabilityLists', () => {
  it('says so when the demonstrator did not answer — no empty column', () => {
    render(<DemoCapabilityLists capabilities={null} />);
    expect(screen.getByRole('status')).toHaveTextContent(
      'showroom.live_invitation.capabilities.unavailable'
    );
    expect(screen.queryByTestId('demo-capabilities')).not.toBeInTheDocument();
  });

  it('renders two named lists, each item under its translated label', () => {
    render(<DemoCapabilityLists capabilities={CAPABILITIES} />);
    const section = screen.getByRole('region', {
      name: 'showroom.live_invitation.capabilities.title',
    });
    const on = within(section).getByRole('list', {
      name: 'showroom.live_invitation.capabilities.enabled',
    });
    const off = within(section).getByRole('list', {
      name: 'showroom.live_invitation.capabilities.disabled',
    });
    expect(
      within(on)
        .getAllByRole('listitem')
        .map(li => li.textContent)
    ).toEqual(['Bookmarks', 'Recherche web']);
    expect(
      within(off)
        .getAllByRole('listitem')
        .map(li => li.textContent)
    ).toEqual(['Enregistrement de réunions', 'Téléversement de fichiers']);
  });

  it('marks each item with its column, so a switched-off feature cannot read as on', () => {
    render(<DemoCapabilityLists capabilities={CAPABILITIES} />);
    expect(screen.getByTestId('demo-capability-on-web_search')).toBeInTheDocument();
    expect(screen.getByTestId('demo-capability-off-meetings')).toBeInTheDocument();
    expect(screen.queryByTestId('demo-capability-on-meetings')).not.toBeInTheDocument();
  });

  it('states where the list comes from, above the columns', () => {
    render(<DemoCapabilityLists capabilities={CAPABILITIES} />);
    const section = screen.getByTestId('demo-capabilities');
    const intro = within(section).getByText('showroom.live_invitation.capabilities.intro');
    const firstList = within(section).getAllByRole('list')[0];
    expect(
      intro.compareDocumentPosition(firstList) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });
});

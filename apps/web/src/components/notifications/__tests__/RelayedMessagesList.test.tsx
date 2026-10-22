import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { RelayedMessagesList, type RelayedMessage } from '../RelayedMessagesList';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) =>
      options?.name ? `${key}: ${options.name}` : key,
  }),
}));

const base: RelayedMessage = {
  id: 'relay',
  peer_display_name: 'Camille',
  direction: 'received',
  content: 'Message conservé',
  occurred_at: '2026-10-15T10:00:00Z',
};

describe('RelayedMessagesList', () => {
  it.each([
    ['received', 'notifications_hub.direction_received', 'notifications_hub.from_peer'],
    ['sent', 'notifications_hub.direction_sent', 'notifications_hub.to_peer'],
  ])('attributes a %s message beside its direction, once', (direction, badge, attribution) => {
    renderWithProviders(
      <RelayedMessagesList
        messages={[{ ...base, direction }]}
        locale="fr-FR"
        presentation="timeline"
      />
    );
    const marker = screen.getByText(badge);
    // The name alone in bold, the words around it plain (owner request
    // 2026-10-21) — the sentence is the translator's, unbroken.
    const name = screen.getByText('Camille');
    expect(name.tagName).toBe('STRONG');
    const peer = name.parentElement;
    if (peer === null) throw new Error('the name has no sentence around it');
    expect(peer).toHaveTextContent(`${attribution}: Camille`);
    expect(marker.closest('div')).toContainElement(peer);
    expect(
      peer.compareDocumentPosition(screen.getByText(base.content!)) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getAllByText(/Camille/)).toHaveLength(1);
    expect(screen.getByRole('listitem').querySelectorAll('svg')).toHaveLength(0);
  });

  it('never reads a display name as markup', () => {
    // A peer chooses their own display name: it is placed as a child, so tags
    // in it stay text — never a `<Trans>` string parsed for elements.
    const { container } = renderWithProviders(
      <RelayedMessagesList
        messages={[{ ...base, peer_display_name: '<i>Camille</i>' }]}
        locale="fr-FR"
        presentation="timeline"
      />
    );
    expect(screen.getByText('<i>Camille</i>').tagName).toBe('STRONG');
    expect(container.querySelector('i')).toBeNull();
  });

  it('retains the no-content explanation without inventing a message', () => {
    renderWithProviders(
      <RelayedMessagesList
        messages={[{ ...base, content: null }]}
        locale="fr-FR"
        presentation="timeline"
      />
    );
    expect(screen.getByText('notifications_hub.message_no_content')).toBeInTheDocument();
    expect(screen.queryByText('Message conservé')).not.toBeInTheDocument();
  });

  it('renders retained relay text as inert text', () => {
    const content = '<script>alert(1)</script> Message';
    const { container } = renderWithProviders(
      <RelayedMessagesList
        messages={[{ ...base, content }]}
        locale="fr-FR"
        presentation="timeline"
      />
    );
    expect(screen.getByText(content)).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
  });
});

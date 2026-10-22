import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';
import { RelationSmsSection } from '../RelationSmsSection';
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { sms_enabled: true } } }),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { timezone: 'Europe/Paris' } }) }));
describe('Relation SMS evidence', () => {
  it('makes the literal SMS itself a link to its exact settings detail', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <RelationSmsSection
        lng="fr"
        available
        total={137}
        messages={[
          {
            id: '10000000-0000-4000-8000-000000000001',
            sender: 'Alice',
            display_name: 'Alice',
            body: '<script>bad()</script>',
            received_at: '2026-10-19T12:30:00Z',
            date_kind: 'received',
            origin: 'iphone',
            identity_source: 'raw',
            identity_state: 'unresolved',
            relation_key: null,
          },
        ]}
      />
    );
    const toggle = screen.getByRole('button', { name: /sms/i });
    expect(toggle).toHaveTextContent('137');
    await user.click(toggle);
    expect(screen.getByText('<script>bad()</script>')).toBeVisible();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/fr/dashboard/settings?section=sms&message=10000000-0000-4000-8000-000000000001'
    );
    expect(screen.getByRole('link')).toContainElement(screen.getByText('<script>bad()</script>'));
    expect(screen.queryByText('relations.sms_open')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /sms.erase/ })).not.toBeInTheDocument();
  });
  it('titles each SMS by when it arrived, like every row of the card, with no icon', async () => {
    // Owner request 2026-10-21: the section already names the person, so its
    // rows carry the dated title — not a second copy of the name and an icon.
    const user = userEvent.setup();
    renderWithProviders(
      <RelationSmsSection
        lng="fr"
        available
        total={1}
        messages={[
          {
            id: '10000000-0000-4000-8000-000000000002',
            sender: '+33600000000',
            display_name: 'Alice Martin',
            body: 'On se voit demain ?',
            received_at: '2026-10-19T12:30:00Z',
            date_kind: 'received',
            origin: 'iphone',
            identity_source: 'contact',
            identity_state: 'resolved',
            relation_key: null,
          },
        ]}
      />
    );
    await user.click(screen.getByRole('button', { name: /sms/i }));

    const article = screen.getByRole('article');
    const heading = within(article).getByRole('heading', { level: 3 });
    expect(heading.querySelectorAll('strong')).toHaveLength(2);
    expect(heading).toHaveTextContent(/2026/);
    // Every SMS here was received: the « received » badge leads the title.
    expect(heading.firstElementChild).toHaveTextContent('relations.peer_message_received');
    expect(article).toHaveAccessibleName(heading.textContent ?? '');
    expect(article.querySelector('svg')).toBeNull();
    expect(within(article).queryByText('Alice Martin')).toBeNull();
    expect(within(article).queryByText('+33600000000')).toBeNull();
    expect(within(article).getByText('On se voit demain ?')).toBeVisible();
  });
  it('distinguishes an unavailable source from an empty archive', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RelationSmsSection lng="fr" available={false} total={0} messages={[]} />);
    await user.click(screen.getByRole('button', { name: /sms/i }));
    expect(screen.getByText('relations.sms_unavailable')).toBeVisible();
  });
});

import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';
import { RelationSmsSection } from '../RelationSmsSection';
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { sms_enabled: true } } }),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { timezone: 'Europe/Paris' } }) }));
describe('Relation SMS evidence', () => {
  it('states exact total, opens literal text, keeps navigation in the archive', async () => {
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
      '/fr/dashboard/sms?message=10000000-0000-4000-8000-000000000001'
    );
  });
  it('distinguishes an unavailable source from an empty archive', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RelationSmsSection lng="fr" available={false} total={0} messages={[]} />);
    await user.click(screen.getByRole('button', { name: /sms/i }));
    expect(screen.getByText('relations.sms_unavailable')).toBeVisible();
  });
});

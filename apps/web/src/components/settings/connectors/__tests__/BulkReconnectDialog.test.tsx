import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { makeConnector } from '@/__tests__/factories';
import { BulkReconnectDialog } from '../BulkReconnectDialog';

const t = (key: string) => key;

describe('BulkReconnectDialog', () => {
  it('requires an explicit selection and submits one request for same-account services', async () => {
    const onSubmit = vi.fn();
    const { user } = renderWithProviders(
      <BulkReconnectDialog
        open
        onOpenChange={vi.fn()}
        provider="google"
        connectors={[
          makeConnector({ id: 'mail', connector_type: 'google_gmail', status: 'error', oauth_grant_id: 'a' }),
          makeConnector({ id: 'calendar', connector_type: 'google_calendar', status: 'error', oauth_grant_id: 'a' }),
        ]}
        busy={false}
        onSubmit={onSubmit}
        t={t}
      />
    );
    const submit = screen.getByRole('button', { name: 'settings.connectors.bulk_reconnect.confirm' });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /Gmail/ }));
    await user.click(screen.getByRole('checkbox', { name: /Calendar/ }));
    await user.click(submit);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith(['google_gmail', 'google_calendar']);
  });

  it('does not mix known different accounts and identifies legacy account as unverified', async () => {
    const onSubmit = vi.fn();
    const { user } = renderWithProviders(
      <BulkReconnectDialog
        open
        onOpenChange={vi.fn()}
        provider="microsoft"
        connectors={[
          makeConnector({ id: 'mail', connector_type: 'microsoft_outlook', status: 'error', oauth_grant_id: 'a', metadata: { oauth_account_email: 'first@example.com' } }),
          makeConnector({ id: 'calendar', connector_type: 'microsoft_calendar', status: 'error', oauth_grant_id: 'b', metadata: { oauth_account_email: 'second@example.com' } }),
          makeConnector({ id: 'tasks', connector_type: 'microsoft_tasks', status: 'error', oauth_grant_id: null }),
        ]}
        busy={false}
        onSubmit={onSubmit}
        t={t}
      />
    );
    expect(screen.getByText('settings.connectors.bulk_reconnect.unknown_account')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: /Outlook/ }));
    expect(screen.getByRole('checkbox', { name: /Calendar/ })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /To Do/ }));
    await user.click(screen.getByRole('button', { name: 'settings.connectors.bulk_reconnect.confirm' }));
    expect(onSubmit).toHaveBeenCalledWith(['microsoft_outlook', 'microsoft_tasks']);
  });
});

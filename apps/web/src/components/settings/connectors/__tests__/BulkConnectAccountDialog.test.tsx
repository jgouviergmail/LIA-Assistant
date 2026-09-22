import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { BulkConnectAccountDialog } from '../BulkConnectAccountDialog';

const t = (key: string) => key;
const accounts = [
  { grantId: 'grant-one', email: 'first@example.com' },
  { grantId: 'grant-two', email: 'second@example.com' },
];

describe('BulkConnectAccountDialog', () => {
  it('requires choosing one known account before submitting', async () => {
    const onSubmit = vi.fn();
    const { user } = renderWithProviders(
      <BulkConnectAccountDialog open provider="microsoft" accounts={accounts}
        busy={false} onOpenChange={vi.fn()} onSubmit={onSubmit} t={t} />
    );
    const submit = screen.getByRole('button', { name: 'settings.connectors.bulk_connect.confirm' });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole('radio', { name: 'second@example.com' }));
    await user.click(submit);
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('grant-two');
  });

  it('can ask the provider to select another account', async () => {
    const onSubmit = vi.fn();
    const { user } = renderWithProviders(
      <BulkConnectAccountDialog open provider="google" accounts={accounts}
        busy={false} onOpenChange={vi.fn()} onSubmit={onSubmit} t={t} />
    );
    await user.click(screen.getByRole('radio', {
      name: 'settings.connectors.bulk_connect.other_account',
    }));
    await user.click(screen.getByRole('button', { name: 'settings.connectors.bulk_connect.confirm' }));
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith(null);
  });
});

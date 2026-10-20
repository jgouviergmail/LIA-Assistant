import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { IngestionApiPanel } from '../IngestionApiPanel';
it.each([
  { copy: 'Copy', close: 'Close', show: 'Show', hide: 'Hide', secret: 'Copy this token now' },
  {
    copy: 'Copier',
    close: 'Fermer',
    show: 'Afficher',
    hide: 'Masquer',
    secret: 'Copiez ce jeton maintenant',
  },
])('names URL and secret controls in $copy locale and never edits a secret', labels => {
  const onCopy = vi.fn(),
    onClearSecret = vi.fn();
  const { rerender } = render(
    <IngestionApiPanel
      endpoints={[
        { id: 'sms-url', label: 'POST SMS', url: 'https://lia.example/api/v1/ingest/message' },
      ]}
      labels={labels}
      secret="pi_private"
      onCopy={onCopy}
      onClearSecret={onClearSecret}
    />
  );
  expect(screen.getByRole('textbox', { name: 'POST SMS' })).toHaveAttribute('readonly');
  expect(screen.getByLabelText(labels.secret)).toHaveAttribute('type', 'password');
  fireEvent.click(screen.getByRole('button', { name: labels.show }));
  expect(screen.getByLabelText(labels.secret)).toHaveAttribute('type', 'text');
  fireEvent.click(screen.getByRole('button', { name: `${labels.copy} · ${labels.secret}` }));
  expect(onCopy).toHaveBeenCalledWith('pi_private');
  fireEvent.click(screen.getByRole('button', { name: labels.close }));
  expect(onClearSecret).toHaveBeenCalledOnce();
  rerender(
    <IngestionApiPanel
      endpoints={[]}
      labels={labels}
      secret={null}
      onCopy={onCopy}
      onClearSecret={onClearSecret}
    />
  );
  expect(screen.queryByDisplayValue('pi_private')).not.toBeInTheDocument();
});

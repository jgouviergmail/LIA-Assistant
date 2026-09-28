/**
 * The « Send by e-mail » triggers (ADR-321): offered only where it can work.
 *
 * Hidden where the page does not offer the action, where a card points at a
 * file that is not ours (an external image) or at a file past its deadline;
 * present otherwise, and the dialog exists only once pressed.
 */

import { fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { EmailShareAvailabilityProvider } from '@/lib/email-share/availability-context';

const { dialog } = vi.hoisted(() => ({ dialog: vi.fn() }));
vi.mock('@/components/email-share/EmailShareDialog', () => ({
  EmailShareDialog: (props: { source: unknown; defaultSubject: string }) => {
    dialog(props);
    return <div role="dialog" />;
  },
}));

import { EmailShareButton } from '../EmailShareButton';
import { FileEmailShareButton } from '../FileEmailShareButton';

const OURS = '/api/v1/attachments/0b8f5c62-7a1e-4d0f-9f5a-3c2b1a0e9d84';

function offered(children: ReactNode) {
  return <EmailShareAvailabilityProvider available>{children}</EmailShareAvailabilityProvider>;
}

describe('EmailShareButton', () => {
  it('is absent where the page does not offer the action', () => {
    renderWithProviders(
      <EmailShareButton
        variant="ghost"
        getSource={() => ({ kind: 'markdown', filename: 'x', text: 'y' })}
        defaultSubject="s"
      />
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('builds the file and opens the dialog only when pressed', () => {
    const source = { kind: 'markdown' as const, filename: 'lia-x', text: '# Hi' };
    const getSource = vi.fn(() => source);
    renderWithProviders(
      offered(<EmailShareButton variant="chip" getSource={getSource} defaultSubject="Sujet" />)
    );
    // An answer's export flattens its HTML: never paid on a render.
    expect(getSource).not.toHaveBeenCalled();
    expect(dialog).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'email_share.button' }));

    expect(getSource).toHaveBeenCalledTimes(1);
    expect(dialog).toHaveBeenCalledWith(
      expect.objectContaining({ source, defaultSubject: 'Sujet' })
    );
  });
});

describe('FileEmailShareButton', () => {
  it('offers our live file under its name', () => {
    renderWithProviders(
      offered(
        <FileEmailShareButton url={OURS} name="plan.pdf" variant="overlay" labelName="plan.pdf" />
      )
    );

    expect(screen.getByRole('button', { name: 'email_share.button_named' })).toBeInTheDocument();
  });

  it('offers nothing for an image that is not one of our files', () => {
    renderWithProviders(
      offered(<FileEmailShareButton url="https://example.com/x.png" name="x" variant="overlay" />)
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers nothing for a file past its deadline', () => {
    renderWithProviders(
      offered(
        <FileEmailShareButton
          url={OURS}
          name="old.png"
          variant="overlay"
          expiresAt="2020-01-01T00:00:00Z"
        />
      )
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

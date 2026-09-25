/**
 * ShareImageButton — offered only where a share could succeed (ADR-316).
 *
 * It sits on EVERY generated image card of the chat, so it must render nothing
 * outside the provider (an archived read-only view), for an image that is not
 * one of our attachments, and must not fetch anything until pressed.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { PeersAvailabilityProvider } from '@/lib/peers/availability-context';

const { recipientsState } = vi.hoisted(() => ({ recipientsState: vi.fn() }));
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipientsState: recipientsState }));

import { ShareImageButton } from '../ShareImageButton';

const OURS = '/api/v1/attachments/0b0e3c3a-6f1d-4c2e-9a51-3d2f1e0c9b8a';

function renderButton(url: string, enabled: boolean | null, expiresAt?: string) {
  const button = (
    <ShareImageButton url={url} title="a lighthouse" expiresAt={expiresAt} className="x" />
  );
  return renderWithProviders(
    enabled === null ? button : <PeersAvailabilityProvider available={enabled}>{button}</PeersAvailabilityProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  recipientsState.mockReturnValue({ recipients: [], loading: false, error: null });
});

describe('ShareImageButton', () => {
  it.each([
    ['outside the provider', OURS, null],
    ['when connections are not offered', OURS, false],
    ['for an image that is not ours', 'https://upload.wikimedia.org/x.png', true],
  ])('renders nothing %s', (_case, url, enabled) => {
    const { container } = renderButton(url, enabled as boolean | null);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for an image that has expired — a share would be refused', () => {
    const { container } = renderButton(OURS, true, '2020-01-01T00:00:00Z');
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the dialog on demand, and only then asks for the connections', async () => {
    const { user } = renderButton(OURS, true);
    expect(recipientsState).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'settings.peers.share_image.button' }));

    expect(
      screen.getByRole('dialog', { name: /settings.peers.share_image.title/ })
    ).toBeInTheDocument();
    expect(recipientsState).toHaveBeenCalledWith(true);
  });
});

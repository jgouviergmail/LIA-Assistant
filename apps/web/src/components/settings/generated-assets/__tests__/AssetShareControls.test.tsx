/**
 * AssetShareControls — the gallery's share action and « shared by » line (ADR-316).
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { PeersAvailabilityProvider } from '@/lib/peers/availability-context';
import type { GeneratedAsset } from '@/types/generated-assets';

vi.mock('@/hooks/usePeerRecipients', () => ({
  usePeerRecipientsState: () => ({ recipients: [], loading: false, error: null }),
}));

import { EmailShareAvailabilityProvider } from '@/lib/email-share/availability-context';

import { EmailAssetButton, SharedByLine, ShareAssetButton } from '../AssetShareControls';

function asset(over: Partial<GeneratedAsset> = {}): GeneratedAsset {
  return {
    id: 'a1',
    title: 'a lighthouse',
    original_filename: 'generated_a1.png',
    mime_type: 'image/png',
    file_size: 10,
    origin: 'generated_image',
    conversation_id: null,
    created_at: '2026-09-24T10:00:00Z',
    expires_at: '2026-09-25T10:00:00Z',
    shared_by_name: null,
    ...over,
  };
}

describe('ShareAssetButton', () => {
  it('is offered on a generated image where connections exist, named after it', () => {
    renderWithProviders(
      <PeersAvailabilityProvider available>
        <ShareAssetButton lng="en" asset={asset()} label="a lighthouse" />
      </PeersAvailabilityProvider>
    );

    expect(
      screen.getByRole('button', { name: 'settings.generated_assets.share' })
    ).toBeInTheDocument();
  });

  it.each([
    ['a screenshot', asset({ origin: 'browser_screenshot' }), true],
    ['a document', asset({ origin: 'generated_document' }), true],
    ['an instance without connections', asset(), false],
  ])('is not offered for %s', (_case, item, enabled) => {
    const { container } = renderWithProviders(
      <PeersAvailabilityProvider available={enabled}>
        <ShareAssetButton lng="en" asset={item} label="x" />
      </PeersAvailabilityProvider>
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('SharedByLine', () => {
  it('names who shared a received copy', () => {
    renderWithProviders(<SharedByLine lng="en" asset={asset({ shared_by_name: 'Gérard' })} />);

    expect(screen.getByTestId('generated-asset-shared-by')).toHaveTextContent(
      'settings.generated_assets.shared_by'
    );
  });

  it('says nothing about an image the person generated', () => {
    const { container } = renderWithProviders(<SharedByLine lng="en" asset={asset()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('EmailAssetButton (ADR-321)', () => {
  const LATER = '2999-01-01T00:00:00Z';

  it.each([
    ['an image', asset({ expires_at: LATER })],
    ['a document', asset({ origin: 'generated_document', expires_at: LATER })],
    ['a capture', asset({ origin: 'browser_screenshot', expires_at: LATER })],
    ['a kept file, which has no deadline', asset({ expires_at: null })],
  ])('is offered for %s, named after it', (_case, item) => {
    renderWithProviders(
      <EmailShareAvailabilityProvider available>
        <EmailAssetButton asset={item} label="a lighthouse" />
      </EmailShareAvailabilityProvider>
    );

    expect(screen.getByRole('button', { name: 'email_share.button_named' })).toBeInTheDocument();
  });

  it('is not offered for a file past its deadline, the cleanup is about to take it', () => {
    renderWithProviders(
      <EmailShareAvailabilityProvider available>
        <EmailAssetButton asset={asset({ expires_at: '2020-01-01T00:00:00Z' })} label="x" />
      </EmailShareAvailabilityProvider>
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

/**
 * The invitation to the live demonstrator, on the showroom page.
 *
 * The owner's rule: a visitor must read every limitation BEFORE reaching the
 * instance. So this block is not a button with a label — it is the list of
 * what the demonstrator is and is not, and the button comes after it.
 *
 * It lives on `/demo`, next to the guided missions, rather than on a page of
 * its own: the guided experience stays the base, the live instance is the
 * complement, and a visitor decides between them in one place.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const apiGet = vi.fn();
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (...args: unknown[]) => apiGet(...args),
}));

import { LiveDemoInvitation } from '@/components/showroom/LiveDemoInvitation';

function mockLink(enabled: boolean, url: string | null, loading = false): void {
  apiGet.mockReturnValue({ data: { enabled, url }, loading, setData: vi.fn() });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('LiveDemoInvitation', () => {
  it('renders nothing while the switch is unknown', () => {
    mockLink(false, null, true);
    const { container } = render(<LiveDemoInvitation lng="fr" />);
    // No flash of an invitation that may not exist: the guided missions
    // below must not jump on the page.
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the operator switched the link off', () => {
    mockLink(false, null);
    const { container } = render(<LiveDemoInvitation lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no URL is served, even if enabled', () => {
    // Defence in depth: the API already withholds the URL when off.
    mockLink(true, null);
    const { container } = render(<LiveDemoInvitation lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('states every limitation before offering the link', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);

    // Every commitment a visitor accepts, each its own line.
    for (const key of [
      'showroom.live_invitation.limits.reduced_edition',
      'showroom.live_invitation.limits.degraded_performance',
      'showroom.live_invitation.limits.ephemeral',
      'showroom.live_invitation.limits.no_sensitive_data',
      'showroom.live_invitation.limits.no_connectors',
      'showroom.live_invitation.limits.account_quota',
      'showroom.live_invitation.limits.daily_capacity',
      'showroom.live_invitation.limits.availability',
      'showroom.live_invitation.limits.email_required',
    ]) {
      expect(await screen.findByText(key)).toBeInTheDocument();
    }
  });

  it('puts the call to action AFTER the limitations, and points at the instance', async () => {
    mockLink(true, 'https://demo.example.org');
    const { container } = render(<LiveDemoInvitation lng="fr" />);

    const link = await screen.findByRole('link', { name: /showroom\.live_invitation\.cta/ });
    expect(link).toHaveAttribute('href', 'https://demo.example.org');
    // Reading order is the point: the limits must precede the button in the
    // DOM, not merely sit near it.
    const limits = screen.getByText('showroom.live_invitation.limits.ephemeral');
    expect(limits.compareDocumentPosition(link)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(container.querySelector('a[target="_blank"]')).toBe(link);
  });

  it('opens the instance safely in a new tab', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);

    const link = await screen.findByRole('link', { name: /showroom\.live_invitation\.cta/ });
    // A cross-origin target=_blank without noopener leaks window.opener.
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
  });

  it('links to the terms, where the demonstrator section lives', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);

    const terms = await screen.findByRole('link', {
      name: 'showroom.live_invitation.terms_link',
    });
    // Section 12 of the terms is what the visitor accepts on arrival.
    expect(terms.getAttribute('href')).toContain('/terms');
  });

  it('reads the link from the anonymous endpoint', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);
    await waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(String(apiGet.mock.calls[0][0])).toBe('/product/public-demo-link');
  });

  it('says it is a reduced edition FIRST', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);

    // Order carries the meaning: a visitor who meets a missing feature
    // without having been told decides the product is unfinished, and no
    // later sentence takes that back.
    const first = await screen.findByText('showroom.live_invitation.limits.reduced_edition');
    const second = screen.getByText('showroom.live_invitation.limits.ephemeral');
    expect(first.compareDocumentPosition(second)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('offers the same way out as the guided missions', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);

    // A plain anchor, like its twin: a client-side push would carry the
    // unhydrated null session onto the landing.
    const back = await screen.findByTestId('live-invitation-back-home');
    expect(back.tagName).toBe('A');
    expect(back).toHaveAttribute('href', expect.stringContaining('/'));
  });

  it('separates the account allowance from the instance one', async () => {
    mockLink(true, 'https://demo.example.org');
    render(<LiveDemoInvitation lng="fr" />);

    // Two different limits with two different consequences: one account
    // waiting for tomorrow is not the whole demonstrator pausing.
    expect(
      await screen.findByText('showroom.live_invitation.limits.account_quota')
    ).toBeInTheDocument();
    expect(
      screen.getByText('showroom.live_invitation.limits.daily_capacity')
    ).toBeInTheDocument();
  });
});

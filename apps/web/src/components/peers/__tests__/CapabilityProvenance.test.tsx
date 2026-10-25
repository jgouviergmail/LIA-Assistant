import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import en from '../../../../locales/en/translation.json';
import { CapabilityProvenance } from '../CapabilityProvenance';
import type { CapabilityShare } from '@/lib/capability-sharing';

vi.unmock('react-i18next');
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'America/New_York' } }),
}));

const share = (over: Partial<CapabilityShare> = {}): CapabilityShare => ({
  recipient_id: '22222222-2222-4222-8222-222222222222',
  recipient_display_name: 'Alice Example',
  shared_at: '2026-10-18T14:30:00Z',
  transfer_id: '33333333-3333-4333-8333-333333333333',
  complete: true,
  can_share_again: false,
  ...over,
});

async function renderIt(ui: React.ReactElement) {
  const i18n = createInstance();
  await i18n.init({
    lng: 'en',
    interpolation: { escapeValue: false },
    resources: { en: { translation: en } },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe('CapabilityProvenance', () => {
  it('draws nothing for a capability nobody shared', async () => {
    const { container } = await renderIt(<CapabilityProvenance lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names the sender of a received copy', async () => {
    await renderIt(
      <CapabilityProvenance
        lng="en"
        origin={{
          sender_display_name: 'Bob Example',
          shared_at: '2026-10-18T14:30:00Z',
          transfer_id: '11111111-1111-4111-8111-111111111111',
        }}
      />
    );
    expect(screen.getByRole('note', { name: /Shared by Bob Example/ })).toBeInTheDocument();
  });

  it('folds the recipients, one line each, closed until opened', async () => {
    const user = userEvent.setup();
    await renderIt(
      <CapabilityProvenance
        lng="en"
        sharedWith={[
          share(),
          share({
            recipient_id: '44444444-4444-4444-8444-444444444444',
            recipient_display_name: null,
            transfer_id: '55555555-5555-4555-8555-555555555555',
            complete: false,
          }),
        ]}
      />
    );
    const toggle = screen.getByText('Shared with');
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.queryByText('Alice Example')).not.toBeInTheDocument();

    await user.click(toggle);

    const lines = screen.getAllByRole('listitem');
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent('Alice Example');
    // The account timezone, not the browser's.
    expect(lines[0].querySelector('time')).toHaveAttribute('dateTime', '2026-10-18T14:30:00Z');
    expect(lines[0]).toHaveTextContent('10:30');
    // A closed account is never named; a partial share says so.
    expect(lines[1]).toHaveTextContent('another user');
    expect(lines[1]).toHaveTextContent('incomplete');
    expect(lines[0]).not.toHaveTextContent('incomplete');
  });

  it('is reached from the keyboard: its toggle is the native summary', async () => {
    // Enter/Space on a <summary> is the browser's own action (proved in the e2e);
    // jsdom does not run it, so this pins the focus order alone.
    const user = userEvent.setup();
    await renderIt(<CapabilityProvenance lng="en" sharedWith={[share()]} />);
    await user.tab();
    expect(document.activeElement?.tagName).toBe('SUMMARY');
    expect(document.activeElement).toHaveTextContent('Shared with');
  });
});

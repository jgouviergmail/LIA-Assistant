/**
 * OpenOffersList (Lot 5-C2) — deciding an offer.
 *
 * Accept records a 👍 THEN opens the chat prefilled (nothing auto-sends);
 * decline records a 👎; a failed decision surfaces a toast and triggers
 * NO navigation and NO reload — the row must stay for a retry.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const { patchMock } = vi.hoisted(() => ({ patchMock: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch: patchMock } }));

const { openChatDeepLink } = vi.hoisted(() => ({ openChatDeepLink: vi.fn() }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink }));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: toastError } }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

import {
  OpenOffersList as OffersView,
  useOfferDecisions,
  type OpenOffersListProps,
} from '../OpenOffersList';

function OpenOffersList(
  props: Omit<OpenOffersListProps, 'decisions'> & { lng: string; onDecided: () => void }
) {
  const decisions = useOfferDecisions(props);
  return <OffersView {...props} decisions={decisions} />;
}
import type { HeartbeatNotification } from '@/hooks/useHeartbeatHistory';

function offer(over: Partial<HeartbeatNotification> = {}): HeartbeatNotification {
  return {
    id: 'offer-1',
    content: 'Tu prépares d’habitude ta revue le soir — je m’en occupe ?',
    created_at: '2026-08-20T08:00:00Z',
    priority: 'low',
    sources_used: '[]',
    decision_reason: null,
    user_feedback: null,
    ...over,
  } as HeartbeatNotification;
}

beforeEach(() => {
  patchMock.mockReset().mockResolvedValue({});
  openChatDeepLink.mockReset();
  toastError.mockReset();
});

describe('OpenOffersList', () => {
  it('accept records a thumbs_up then opens the prefilled chat', async () => {
    const onDecided = vi.fn();
    render(<OpenOffersList offers={[offer()]} lng="fr" locale="fr-FR" onDecided={onDecided} />);

    fireEvent.click(
      screen.getByRole('button', { name: 'notifications_hub.sections.offers.accept' })
    );

    await waitFor(() => expect(onDecided).toHaveBeenCalled());
    expect(patchMock).toHaveBeenCalledWith('/heartbeat/notifications/offer-1/feedback', {
      feedback: 'thumbs_up',
    });
    expect(openChatDeepLink).toHaveBeenCalledTimes(1);
  });

  it('decline records a thumbs_down and never navigates', async () => {
    const onDecided = vi.fn();
    render(<OpenOffersList offers={[offer()]} lng="fr" locale="fr-FR" onDecided={onDecided} />);

    fireEvent.click(
      screen.getByRole('button', { name: 'notifications_hub.sections.offers.dismiss' })
    );

    await waitFor(() => expect(onDecided).toHaveBeenCalled());
    expect(patchMock).toHaveBeenCalledWith('/heartbeat/notifications/offer-1/feedback', {
      feedback: 'thumbs_down',
    });
    expect(openChatDeepLink).not.toHaveBeenCalled();
  });

  it('a failed decision surfaces a toast — no navigation, no reload', async () => {
    patchMock.mockRejectedValue(new Error('boom'));
    const onDecided = vi.fn();
    render(<OpenOffersList offers={[offer()]} lng="fr" locale="fr-FR" onDecided={onDecided} />);

    fireEvent.click(
      screen.getByRole('button', { name: 'notifications_hub.sections.offers.accept' })
    );

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(openChatDeepLink).not.toHaveBeenCalled();
    expect(onDecided).not.toHaveBeenCalled();
  });
});

it('prevents repeated decisions while the first request is pending', async () => {
  let complete!: () => void;
  patchMock.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        complete = resolve;
      })
  );
  const onDecided = vi.fn();
  render(<OpenOffersList offers={[offer()]} lng="fr" locale="fr-FR" onDecided={onDecided} />);
  const accept = screen.getByRole('button', { name: 'notifications_hub.sections.offers.accept' });
  fireEvent.click(accept);
  expect(accept).toHaveAttribute('aria-disabled', 'true');
  expect(
    screen.getByRole('button', { name: 'notifications_hub.sections.offers.dismiss' })
  ).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(accept);
  expect(patchMock).toHaveBeenCalledTimes(1);
  expect(openChatDeepLink).not.toHaveBeenCalled();
  complete();
  await waitFor(() => expect(onDecided).toHaveBeenCalledTimes(1));
});

it('does not let a successful decision be repeated while stale data remains displayed', async () => {
  const onDecided = vi.fn();
  render(<OpenOffersList offers={[offer()]} lng="fr" locale="fr-FR" onDecided={onDecided} />);
  const decline = screen.getByRole('button', { name: 'notifications_hub.sections.offers.dismiss' });
  fireEvent.click(decline);
  await waitFor(() => expect(onDecided).toHaveBeenCalledTimes(1));
  expect(decline).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(decline);
  expect(patchMock).toHaveBeenCalledTimes(1);
});

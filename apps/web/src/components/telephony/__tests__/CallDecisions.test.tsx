/**
 * CallDecisions — what the callee proposed, and who gets to accept it.
 *
 * The extraction has always held a proposed date, a place, a surcharge and
 * anything the assistant deliberately did not settle. None of it was shown, so
 * a price increase mentioned on a call placed for the user existed in the
 * database and nowhere they could read it.
 *
 * The rule that comes with publishing it: publishing is ALL that happens. The
 * one action is a `?draft=` that prefills the composer — a cost or an option
 * someone else proposed is a claim to arbitrate, never an instruction, which is
 * precisely why the assistant flagged it instead of agreeing on the call.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { StructuredCallData } from '@/types/telephony';

const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

import { CallDecisions } from '../CallDecisions';

const FULL: StructuredCallData = {
  agreed: true,
  proposed_datetime: '2026-08-05T19:00:00',
  location: 'Le Jardin, terrasse',
  additional_costs: 'supplément terrasse +3 €',
  pending_user_decision: 'menu enfant ou demi-portion ?',
};

function render(data: StructuredCallData | null, actionable = true) {
  return renderWithProviders(
    <CallDecisions
      data={data}
      calleeDisplay="Le Jardin"
      objective="Réserver une table mardi"
      lng="fr"
      actionable={actionable}
    />
  );
}

beforeEach(() => openChat.mockClear());

describe('CallDecisions', () => {
  it('renders nothing when the call produced no decision to make', () => {
    const { container } = render({ agreed: true, notes: 'RAS' });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing at all without an extraction', () => {
    const { container } = render(null);
    expect(container).toBeEmptyDOMElement();
  });

  it('states the cost the callee mentioned, and that nothing was accepted', () => {
    render(FULL);

    expect(
      screen.getByText(/decisions\.extra_cost\|cost=supplément terrasse \+3 €/)
    ).toBeInTheDocument();
  });

  it('states what was left for the reader to decide', () => {
    render(FULL);

    expect(
      screen.getByText(/decisions\.pending\|question=menu enfant ou demi-portion/)
    ).toBeInTheDocument();
  });

  it('says PROPOSED, never booked', () => {
    // The assistant did not accept the slot; the wording must not imply it did.
    render(FULL);

    expect(screen.getByText(/decisions\.proposed\|/)).toBeInTheDocument();
  });

  it('names the gap rather than leaving a blank half-sentence', () => {
    render({ proposed_datetime: '2026-08-05T19:00:00', location: null });

    expect(screen.getByText(/where=settings\.telephony\.decisions\.no_place/)).toBeInTheDocument();
  });

  it('prefills a meeting draft carrying the subject, the invitee and the place', async () => {
    const { user } = render(FULL);

    await user.click(screen.getByRole('button', { name: /decisions\.plan_meeting/ }));

    const url = decodeURIComponent(openChat.mock.calls[0][0] as string);
    expect(url.startsWith('/fr/dashboard/chat?draft=')).toBe(true);
    expect(url).toContain('subject=Réserver une table mardi');
    expect(url).toContain('invitee=Le Jardin');
    expect(url).toContain('where=Le Jardin, terrasse');
  });

  it('never auto-sends — a proposal is not an instruction', async () => {
    const { user } = render(FULL);

    for (const button of screen.getAllByRole('button')) {
      await user.click(button);
    }

    expect(openChat).toHaveBeenCalled();
    for (const [url] of openChat.mock.calls) {
      expect(url as string).not.toContain('?intent=');
    }
  });

  it('offers no action on a read-only surface', () => {
    render(FULL, false);

    expect(screen.queryAllByRole('button')).toHaveLength(0);
    // …but the facts are still stated: the chat bubble reads them too.
    expect(screen.getByText(/decisions\.extra_cost\|/)).toBeInTheDocument();
  });

  it('offers no meeting draft when neither a date nor a place was proposed', () => {
    render({ additional_costs: '+3 €' });

    expect(screen.queryByRole('button', { name: /plan_meeting/ })).toBeNull();
  });
});

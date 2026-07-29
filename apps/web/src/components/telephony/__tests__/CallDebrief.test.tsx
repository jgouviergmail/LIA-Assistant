/**
 * CallDebrief (T01) — the structured debrief of a completed call.
 *
 * What must hold:
 *  - a null-content debrief renders NOTHING (absence, not noise);
 *  - lists render under their titled sections;
 *  - INFORMATIONAL posture (chat) carries zero action chips;
 *  - ACTIONABLE posture (settings) deep-links follow-ups as `?intent=` and
 *    the draft as `?draft=` (ADR-173: a draft needs the user's own review).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { PhoneCallDebrief } from '@/types/telephony';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
// Echo translator that SHOWS interpolations — the intent must carry the item.
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

import { CallDebrief } from '../CallDebrief';

const FULL: PhoneCallDebrief = {
  commitments: ['Marie confirme mardi 19h.'],
  follow_up_tasks: ['Réserver la table en terrasse.'],
  follow_up_reminders: ['Rappeler mardi 18h pour confirmer.'],
  follow_up_draft: 'Bonjour Marie, je confirme mardi 19h.',
  uncertainties: ['Le supplément terrasse n’est pas confirmé.'],
};

beforeEach(() => {
  push.mockClear();
});

describe('CallDebrief', () => {
  it('renders nothing for an all-empty debrief', () => {
    const { container } = renderWithProviders(
      <CallDebrief debrief={{ commitments: [], follow_up_tasks: [] }} lng="fr" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders every populated section', () => {
    renderWithProviders(<CallDebrief debrief={FULL} lng="fr" />);
    expect(screen.getByText('Marie confirme mardi 19h.')).toBeInTheDocument();
    expect(screen.getByText('Réserver la table en terrasse.')).toBeInTheDocument();
    expect(screen.getByText('Le supplément terrasse n’est pas confirmé.')).toBeInTheDocument();
    expect(screen.getByText('Bonjour Marie, je confirme mardi 19h.')).toBeInTheDocument();
  });

  it('carries ZERO action chips in the informational posture (chat)', () => {
    renderWithProviders(<CallDebrief debrief={FULL} lng="fr" />);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('deep-links a follow-up task as an executable intent when actionable', async () => {
    const { user } = renderWithProviders(<CallDebrief debrief={FULL} lng="fr" actionable />);

    await user.click(
      screen.getByRole('button', { name: /settings.telephony.debrief.intent_task/ })
    );

    const url = push.mock.calls[0][0] as string;
    expect(url.startsWith('/fr/dashboard/chat?intent=')).toBe(true);
    expect(decodeURIComponent(url)).toContain('Réserver la table en terrasse.');
  });

  it('prefills the follow-up draft (never auto-sends someone else a message)', async () => {
    const { user } = renderWithProviders(<CallDebrief debrief={FULL} lng="fr" actionable />);

    await user.click(screen.getByRole('button', { name: 'settings.telephony.debrief.use_draft' }));

    const url = push.mock.calls[0][0] as string;
    expect(url.startsWith('/fr/dashboard/chat?draft=')).toBe(true);
  });
});

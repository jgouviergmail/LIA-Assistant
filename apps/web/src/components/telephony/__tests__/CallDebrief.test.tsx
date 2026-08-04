/**
 * CallDebrief (T01) — the structured debrief of a completed call.
 *
 * What must hold:
 *  - a null-content debrief renders NOTHING (absence, not noise);
 *  - lists render under their titled sections;
 *  - INFORMATIONAL posture (chat) carries zero action chips;
 *  - ACTIONABLE posture (settings) PREFILLS every follow-up as `?draft=` and
 *    never auto-sends: a debrief reports what someone else proposed, and
 *    `?intent=` would have executed it (ADR-173) with no confirmation left in
 *    the chain for a reminder.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { PhoneCallDebrief } from '@/types/telephony';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

// Chat deep links are REAL navigations since 2026-08-01 (ADR-192): the App
// Router restored the search params of the entry it already held, so a second
// deep link in a session left with the FIRST one's URL. The oracle is the same
// href — only the door changed.
const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
}));
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
  key_points: ['La table du mardi est disponible.'],
  commitments: ['Marie confirme mardi 19h.'],
  follow_up_tasks: ['Réserver la table en terrasse.'],
  follow_up_reminders: ['Rappeler mardi 18h pour confirmer.'],
  follow_up_draft: 'Bonjour Marie, je confirme mardi 19h.',
  uncertainties: ['Le supplément terrasse n’est pas confirmé.'],
};

beforeEach(() => {
  openChat.mockClear();
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
    expect(screen.getByText('La table du mardi est disponible.')).toBeInTheDocument();
    expect(screen.getByText('Marie confirme mardi 19h.')).toBeInTheDocument();
    expect(screen.getByText('Réserver la table en terrasse.')).toBeInTheDocument();
    expect(screen.getByText('Le supplément terrasse n’est pas confirmé.')).toBeInTheDocument();
    expect(screen.getByText('Bonjour Marie, je confirme mardi 19h.')).toBeInTheDocument();
  });

  it('renders an information-call debrief that is key-points only', () => {
    // The prod 2026-07-29 case: no commitments/tasks/reminders/draft, only the
    // structured findings — this must render, not fall back to nothing.
    renderWithProviders(
      <CallDebrief
        debrief={{ key_points: ['Samedi : rien de prévu', 'Dimanche : amis vers midi ou 16h'] }}
        lng="fr"
      />
    );
    expect(screen.getByText('Samedi : rien de prévu')).toBeInTheDocument();
    expect(screen.getByText('Dimanche : amis vers midi ou 16h')).toBeInTheDocument();
  });

  it('carries ZERO action chips in the informational posture (chat)', () => {
    renderWithProviders(<CallDebrief debrief={FULL} lng="fr" />);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  // A debrief reports what SOMEONE ELSE said on a call the assistant placed.
  // Nothing in it may become an action without the user saying so: an option,
  // a surcharge or a commitment proposed by the other party is a claim to
  // review, never an instruction to execute.
  //
  // `?intent=` is AUTO-SENT (ADR-173), and `create_reminder_tool` writes
  // straight to the database with no HITL draft of its own — only
  // `cancel_reminder_tool` has one. A reminder chip on `?intent=` therefore
  // created the reminder with no confirmation anywhere in the chain. And even
  // where a tool DOES hold a draft, prose alone cannot promise which tool the
  // planner will pick, so the guarantee could not be relied upon.
  //
  // Every debrief action is therefore a `?draft=`: the sentence lands in the
  // composer, the user reads it and presses Enter. Tool-level HITL still
  // applies afterwards — this adds a step, it removes none.
  it.each([
    ['task', /settings.telephony.debrief.intent_task/, 'Réserver la table en terrasse.'],
    [
      'reminder',
      /settings.telephony.debrief.intent_reminder/,
      'Rappeler mardi 18h pour confirmer.',
    ],
  ])('prefills the follow-up %s instead of executing it', async (_kind, name, text) => {
    const { user } = renderWithProviders(<CallDebrief debrief={FULL} lng="fr" actionable />);

    await user.click(screen.getByRole('button', { name }));

    const url = openChat.mock.calls[0][0] as string;
    expect(url.startsWith('/fr/dashboard/chat?draft=')).toBe(true);
    expect(url).not.toContain('?intent=');
    expect(decodeURIComponent(url)).toContain(text);
  });

  it('names the chip after what the CLICK does, not after the sentence', async () => {
    // "Create a task: …" as a button name promised the creation. The click
    // only puts that sentence in the composer, so the name says so — and a
    // screen-reader user is not told an action happened that did not.
    renderWithProviders(<CallDebrief debrief={FULL} lng="fr" actionable />);

    const chip = screen.getByRole('button', {
      name: /prefill_aria\|sentence=settings\.telephony\.debrief\.intent_task/,
    });

    // The wrapper leads (what the click does), the sentence follows (what it
    // will write) — and the item is still carried, so the name is specific to
    // this row rather than shared by every chip of the list.
    expect(chip).toHaveAccessibleName(
      'settings.telephony.debrief.prefill_aria|sentence=settings.telephony.debrief.intent_task|item=Réserver la table en terrasse.'
    );
  });

  it('never auto-sends anything from a debrief, whatever the section', async () => {
    // A single guard over the whole card: a section added later cannot
    // reintroduce an auto-sent chip without failing here.
    const { user } = renderWithProviders(<CallDebrief debrief={FULL} lng="fr" actionable />);

    for (const button of screen.getAllByRole('button')) {
      await user.click(button);
    }

    expect(openChat).toHaveBeenCalled();
    for (const [url] of openChat.mock.calls) {
      expect(url as string).not.toContain('?intent=');
    }
  });

  it('prefills the follow-up draft (never auto-sends someone else a message)', async () => {
    const { user } = renderWithProviders(<CallDebrief debrief={FULL} lng="fr" actionable />);

    await user.click(screen.getByRole('button', { name: 'settings.telephony.debrief.use_draft' }));

    const url = openChat.mock.calls[0][0] as string;
    expect(url.startsWith('/fr/dashboard/chat?draft=')).toBe(true);
  });
});

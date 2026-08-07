/**
 * MissionActions — layout contract and the actions themselves.
 *
 * Owner request 2026-08-07: "Et maintenant ?" plus the four calls to action
 * plus the two utilities ("Rejouer la mission", "Toutes les missions") are all
 * centred horizontally, with more vertical breathing room. It closes a mission,
 * so it reads as a conclusion, not as a left-aligned toolbar continuing the
 * storyboard.
 *
 * Alignment is a presentational requirement, so the class IS the contract here
 * — jsdom computes no layout. The behavioural half (what each control does,
 * where it points, what it reports) is asserted the usual way below.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MissionActions, type MissionActionsProps } from '../MissionActions';
import type { ShowroomProofLinks } from '../proof-links';
import type { ShowroomCtaKind } from '../useShowroomMission';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const LINKS: ShowroomProofLinks = {
  isImmutable: false,
  links: [
    {
      id: 'routing',
      labelKey: 'showroom.proof.routing',
      kind: 'product-core',
      url: 'https://example.com/routing',
    },
  ],
};

function setup(over: Partial<MissionActionsProps> = {}) {
  // Spies declared with their real signatures, so `.mock.calls` stays typed —
  // spreading them into a props object first would widen them to the union of
  // "spy or plain callback" and lose it (apps/web CLAUDE.md: tests stay
  // type-safe, no `as any`).
  const spies = {
    onRestart: vi.fn<() => void>(),
    onChangeMission: vi.fn<() => void>(),
    onProofOpened: vi.fn<() => void>(),
    onCta: vi.fn<(kind: ShowroomCtaKind) => void>(),
  };
  const props: MissionActionsProps = { proofLinks: LINKS, ...spies, ...over };
  const utils = render(<MissionActions {...props} />);
  return { ...utils, spies, user: userEvent.setup() };
}

/** The two rows of controls, in document order. */
function rows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="showroom-actions-row"]'));
}

describe('MissionActions — the closing block is centred', () => {
  it('centres the heading', () => {
    setup();

    expect(screen.getByText('showroom.actions.title').className).toContain('text-center');
  });

  it('centres both rows of controls', () => {
    setup();

    const found = rows();
    expect(found).toHaveLength(2);
    for (const row of found) expect(row.className).toContain('justify-center');
  });

  it('keeps the controls wrapping, so a phone never clips one off', () => {
    setup();

    const found = rows();
    // Asserted before the loop: over an empty list the loop proves nothing,
    // and a selector that stops matching would leave this test green forever.
    expect(found).toHaveLength(2);
    for (const row of found) expect(row.className).toContain('flex-wrap');
  });

  it('breathes vertically', () => {
    // `space-y-3` was the condensed original; anything tighter than 4 puts the
    // conclusion back inside the storyboard's rhythm.
    const { container } = setup();

    const block = container.firstElementChild as HTMLElement;

    expect(block.className).toMatch(/space-y-[5-9]/);
  });
});

describe('MissionActions — what the controls actually do', () => {
  it('offers the install guide as the primary, pointing at the quick start', () => {
    setup();

    const link = screen.getByTestId('showroom-cta-install');

    expect(link).toHaveAttribute('href', expect.stringContaining('#quick-start'));
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('reports each call to action under its own kind', async () => {
    const { spies, user } = setup();

    await user.click(screen.getByTestId('showroom-cta-install'));
    await user.click(screen.getByTestId('showroom-cta-release'));
    await user.click(screen.getByTestId('showroom-cta-source'));

    expect(spies.onCta.mock.calls.map(([kind]) => kind)).toEqual([
      'install_guide',
      'release',
      'source',
    ]);
  });

  it('replays the mission', async () => {
    const { spies, user } = setup();

    await user.click(screen.getByTestId('showroom-restart'));

    expect(spies.onRestart).toHaveBeenCalledTimes(1);
  });

  it('goes back to the mission list', async () => {
    const { spies, user } = setup();

    await user.click(screen.getByTestId('showroom-change-mission'));

    expect(spies.onChangeMission).toHaveBeenCalledTimes(1);
  });

  it('opens every external link in a new tab, safely', () => {
    setup();

    for (const id of ['showroom-cta-install', 'showroom-cta-release', 'showroom-cta-source']) {
      const link = screen.getByTestId(id);
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
    }
  });
});

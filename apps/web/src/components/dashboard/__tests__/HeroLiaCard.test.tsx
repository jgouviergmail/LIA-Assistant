/**
 * The current animated identity is decorative. One smaller opposite portrait
 * selects the shared gender preference, with no extra fetch or audio owner.
 * Greeting output remains inert and its synthesis subtree stays mounted.
 */

import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  installSpiritBrowser,
  SpiritIntersectionObserver,
} from '@/components/spirit/__tests__/browser';
import { activeFrameSubscribers } from '@/components/eyes/rig/scheduler';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { useLiaGender } from '@/hooks/useLiaGender';

import { HeroLiaCard } from '../HeroLiaCard';
import type { TextSection } from '@/types/briefing';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const FEMALE = 'dashboard.avatar_picker.female';
const MALE = 'dashboard.avatar_picker.male';
let browser: ReturnType<typeof installSpiritBrowser>;
const fetchMock = vi.fn<typeof fetch>();

// Load the real renderer once before DOM interactions; production remains lazy.
beforeAll(async () => {
  await import('@/components/psyche/SelectedCompanionPortrait');
});

beforeEach(() => {
  browser = installSpiritBrowser();
  document.cookie = 'lia_gender=female; path=/';
  useEyesWidgetStore.getState().reset();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.cookie = 'lia_gender=female; path=/';
});

async function portrait(container: HTMLElement) {
  return waitFor(() => {
    const target = container.querySelector<HTMLElement>('[data-companion-portrait]');
    if (!target) throw new Error('Selected animated portrait missing');
    return target;
  });
}

function showPortrait(target: HTMLElement, visible = true) {
  const observer = SpiritIntersectionObserver.instances.find(instance =>
    instance.targets.has(target)
  );
  if (!observer) throw new Error('Portrait visibility observer missing');
  observer.notify(target, visible);
}

function makeGreeting(text: string): TextSection {
  return { text, generated_at: '2026-07-03T08:00:00Z', usage: null };
}

/** The floating avatar reads this same real hook and change event. */
function OtherMountedIdentity() {
  const { isMale } = useLiaGender();
  return <output aria-label="Other mounted identity">{isMale ? 'male' : 'female'}</output>;
}

describe('HeroLiaCard — greeting is inert', () => {
  it('renders a hostile event title as literal text without creating a source element', () => {
    const payload = '<img src=x onerror=alert(1)> Bonjour Jérôme';
    const { container, getByText } = render(<HeroLiaCard greeting={makeGreeting(payload)} />);
    expect(getByText(payload).querySelector('img')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
    expect(getByText(payload)).toHaveTextContent(payload);
  });

  it('does not execute script tags echoed in the greeting', () => {
    const { container } = render(
      <HeroLiaCard greeting={makeGreeting('Bonjour <script>window.hacked = true;</script>')} />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(window).not.toHaveProperty('hacked');
  });

  it('renders a plain greeting normally', () => {
    const { getByText } = render(
      <HeroLiaCard greeting={makeGreeting('Bonjour Jérôme, journée chargée !')} />
    );
    expect(getByText('Bonjour Jérôme, journée chargée !')).toBeVisible();
  });
});

describe('HeroLiaCard — one opposite portrait selects the identity', () => {
  it('makes the current identity noninteractive and offers only the opposite portrait as a button', async () => {
    const user = userEvent.setup();
    const { getByRole, getAllByRole, queryByLabelText } = render(<HeroLiaCard />);
    const main = getByRole('img', { name: FEMALE });
    const face = await portrait(main);
    expect(main.closest('button, a')).toBeNull();
    expect(main).not.toHaveAttribute('tabindex');
    await user.click(main);
    expect(face).toHaveAttribute('data-portrait-variant', 'female');
    expect(document.cookie).toContain('lia_gender=female');
    const alternate = getByRole('button', { name: MALE });
    expect(getAllByRole('button')).toEqual([alternate]);
    expect(await portrait(alternate)).toHaveAttribute('data-portrait-variant', 'male');
    const pair = getByRole('group', { name: 'dashboard.avatar_picker.group_label' });
    expect(pair).toContainElement(main);
    expect(pair).toContainElement(alternate);
    expect(queryByLabelText('dashboard.actions.toggle_avatar')).toBeNull();
  });

  it('swaps both native portraits in either direction with a click and synchronizes other mounted consumers', async () => {
    const user = userEvent.setup();
    const { getByRole, getByLabelText } = render(
      <>
        <HeroLiaCard />
        <OtherMountedIdentity />
      </>
    );
    const main = getByRole('img', { name: FEMALE });
    const mainFace = await portrait(main);
    const swap = getByRole('button', { name: MALE });
    const smallFace = await portrait(swap);

    await user.click(swap);
    expect(getByRole('img', { name: MALE })).toBe(main);
    expect(mainFace).toHaveAttribute('data-portrait-variant', 'male');
    expect(smallFace).toHaveAttribute('data-portrait-variant', 'female');
    expect(getByRole('button', { name: FEMALE })).toBe(swap);
    expect(document.cookie).toContain('lia_gender=male');
    expect(getByLabelText('Other mounted identity')).toHaveTextContent('male');

    await user.click(swap);
    expect(mainFace).toHaveAttribute('data-portrait-variant', 'female');
    expect(smallFace).toHaveAttribute('data-portrait-variant', 'male');
    expect(getByRole('button', { name: MALE })).toBe(swap);
    expect(document.cookie).toContain('lia_gender=female');
    expect(getByLabelText('Other mounted identity')).toHaveTextContent('female');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps focus on the same opposite-portrait button for Enter and Space swaps', async () => {
    const user = userEvent.setup();
    const { getByRole } = render(<HeroLiaCard />);
    const mainFace = await portrait(getByRole('img', { name: FEMALE }));
    const swap = getByRole('button', { name: MALE });
    const smallFace = await portrait(swap);
    await user.tab();
    expect(swap).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(mainFace).toHaveAttribute('data-portrait-variant', 'male');
    expect(smallFace).toHaveAttribute('data-portrait-variant', 'female');
    expect(swap).toHaveAccessibleName(FEMALE);
    expect(swap).toHaveFocus();
    await user.keyboard(' ');
    expect(mainFace).toHaveAttribute('data-portrait-variant', 'female');
    expect(smallFace).toHaveAttribute('data-portrait-variant', 'male');
    expect(swap).toHaveAccessibleName(MALE);
    expect(swap).toHaveFocus();
  });

  it('reads an existing masculine preference and offers the feminine identity beneath it', async () => {
    document.cookie = 'lia_gender=male; path=/';
    const { getByRole } = render(<HeroLiaCard />);
    expect(await portrait(getByRole('img', { name: MALE }))).toHaveAttribute(
      'data-portrait-variant',
      'male'
    );
    expect(await portrait(getByRole('button', { name: FEMALE }))).toHaveAttribute(
      'data-portrait-variant',
      'female'
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('follows the same style and external gender change for both portraits without a fetch', async () => {
    const { getByRole } = render(<HeroLiaCard />);
    const main = getByRole('img', { name: FEMALE });
    const mainFace = await portrait(main);
    const swap = getByRole('button', { name: MALE });
    const smallFace = await portrait(swap);
    act(() => {
      useEyesWidgetStore.getState().setStyle('boulon');
      document.cookie = 'lia_gender=male; path=/';
      window.dispatchEvent(new Event('lia-gender-change'));
    });
    expect(mainFace).toHaveAttribute('data-companion-portrait', 'boulon');
    expect(smallFace).toHaveAttribute('data-companion-portrait', 'boulon');
    expect(mainFace).toHaveAttribute('data-portrait-variant', 'male');
    expect(smallFace).toHaveAttribute('data-portrait-variant', 'female');
    expect(getByRole('img', { name: MALE })).toBe(main);
    expect(getByRole('button', { name: FEMALE })).toBe(swap);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('HeroLiaCard — existing motion and lifecycle boundaries', () => {
  it('keeps the alternate still and runs only the visible main portrait on the shared clock', async () => {
    const { getByRole, unmount } = render(<HeroLiaCard />);
    const face = await portrait(getByRole('img', { name: FEMALE }));
    const alternate = await portrait(getByRole('button', { name: MALE }));
    act(() => showPortrait(alternate));
    expect(activeFrameSubscribers()).toBe(0);
    act(() => showPortrait(face));
    expect(activeFrameSubscribers()).toBe(1);
    act(() => showPortrait(face, false));
    expect(activeFrameSubscribers()).toBe(0);
    act(() => showPortrait(face));
    expect(activeFrameSubscribers()).toBe(1);
    unmount();
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('keeps both native identities still under reduced motion and wakes only the main portrait afterwards', async () => {
    act(() => browser.setMotion(true));
    const { getByRole } = render(<HeroLiaCard />);
    const face = await portrait(getByRole('img', { name: FEMALE }));
    const alternate = await portrait(getByRole('button', { name: MALE }));
    act(() => {
      showPortrait(face);
      showPortrait(alternate);
    });
    expect(activeFrameSubscribers()).toBe(0);
    act(() => browser.setMotion(false));
    expect(activeFrameSubscribers()).toBe(1);
  });

  it('keeps both portrait nodes and the existing synthesis subtree mounted across greeting and identity changes', async () => {
    const user = userEvent.setup();
    const { getByRole, rerender } = render(
      <HeroLiaCard greeting={makeGreeting('Bonjour')}>
        <input aria-label="Existing synthesis owner" defaultValue="kept" />
      </HeroLiaCard>
    );
    const mainFace = await portrait(getByRole('img', { name: FEMALE }));
    const swap = getByRole('button', { name: MALE });
    const smallFace = await portrait(swap);
    const existing = getByRole('textbox', { name: 'Existing synthesis owner' });
    await user.clear(existing);
    await user.type(existing, 'Unchanged synthesis lifetime');
    rerender(
      <HeroLiaCard greeting={makeGreeting('Bienvenue')} isLoadingGreeting>
        <input aria-label="Existing synthesis owner" defaultValue="kept" />
      </HeroLiaCard>
    );
    expect(await portrait(getByRole('img', { name: FEMALE }))).toBe(mainFace);
    expect(await portrait(swap)).toBe(smallFace);
    expect(getByRole('textbox', { name: 'Existing synthesis owner' })).toBe(existing);
    expect(existing).toHaveValue('Unchanged synthesis lifetime');
    expect(existing).toHaveFocus();
    await user.click(swap);
    expect(getByRole('textbox', { name: 'Existing synthesis owner' })).toBe(existing);
    expect(existing).toHaveValue('Unchanged synthesis lifetime');
  });
});

it('offers Chat before Services as localized navigation links', () => {
  const { getAllByRole } = render(<HeroLiaCard />);
  expect(getAllByRole('link').map(link => link.getAttribute('href'))).toEqual([
    '/fr/dashboard/chat',
    '/fr/dashboard/settings?section=connectors',
  ]);
});

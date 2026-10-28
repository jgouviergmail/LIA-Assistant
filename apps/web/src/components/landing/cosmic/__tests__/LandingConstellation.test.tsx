import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import type { Language } from '@/i18n/settings';
import { mapsDataFixture } from '@/lib/maps/__tests__/fixtures';
import { buildBrickMap } from '@/lib/maps/model';
import { LandingConstellation } from '../LandingConstellation';

vi.unmock('react-i18next');

const map = buildBrickMap(mapsDataFixture(), 'functional');

async function renderLanding(lng: Language = 'fr') {
  const i18n = createInstance();
  await i18n.init({
    lng,
    resources: { fr: { translation: fr }, en: { translation: en } },
    interpolation: { escapeValue: false },
  });
  const user = userEvent.setup();
  const view = render(
    <I18nextProvider i18n={i18n}>
      <LandingConstellation map={map} lng={lng} />
    </I18nextProvider>
  );
  const words = lng === 'en' ? en.maps : fr.maps;
  const constellation = screen.getByRole('group', { name: words.functional.constellation_label });
  const node = (name: string) =>
    within(constellation).getByRole('button', { name: new RegExp(`^${name} — `) });
  return { user, words, constellation, node, ...view };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/#gallery');
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: true }))
  );
});

afterEach(() => {
  window.history.replaceState(null, '', '/');
  vi.unstubAllGlobals();
});

describe('LandingConstellation', () => {
  it.each(['fr', 'en'] as const)(
    'names the interactive panels in %s and opens a brick from the keyboard',
    async lng => {
      const { user, words, node } = await renderLanding(lng);
      expect(screen.getByRole('heading', { name: words.player.title })).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: words.functional.legend_title })
      ).toBeInTheDocument();
      expect(
        screen.getByRole('searchbox', { name: words.common.search_label })
      ).toBeInTheDocument();
      expect(
        screen.getByRole('region', { name: words.functional.constellation_label })
      ).toHaveAttribute('tabindex', '0');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(window.location.hash).toBe('#gallery');

      const conversation = node('Conversation');
      act(() => conversation.focus());
      expect(conversation).toHaveClass('is-on');
      expect(node('Mémoire')).toHaveClass('is-near');
      await user.keyboard('{Enter}');

      const dialog = await screen.findByRole('dialog', { name: 'Conversation' });
      expect(window.location.hash).toBe('#f.one');
      expect(within(dialog).getByRole('link', { name: 'Mémoire' })).toHaveAttribute(
        'href',
        '#f.two'
      );
      expect(within(dialog).getByRole('link', { name: 'FastAPI' })).toHaveAttribute(
        'href',
        `${lng === 'en' ? '/en' : ''}/maps/technical#t.one`
      );
      expect(screen.getByRole('button', { name: words.drawer.close })).toHaveFocus();
      await user.keyboard('{Escape}');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(window.location.hash).toBe('');
      expect(conversation).toHaveFocus();
    }
  );

  it('isolates a family, plays a journey and stops it when opening a brick', async () => {
    const { user, words, node } = await renderLanding();
    const family = screen.getByRole('button', { name: /^Prévenir/ });
    await user.click(family);
    expect(family).toHaveAttribute('aria-pressed', 'true');
    expect(node('Notifications')).toHaveClass('is-on');
    expect(node('Conversation')).not.toHaveClass('is-on');
    await user.click(family);
    expect(family).toHaveAttribute('aria-pressed', 'false');

    const journeys = screen.getByRole('list', { name: words.player.flows_label });
    await user.click(within(journeys).getByRole('button', { name: 'Une demande' }));
    expect(screen.getByRole('button', { name: words.player.play })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: words.player.pause })).not.toBeInTheDocument();
    expect(node('Conversation')).toHaveClass('is-on');
    await user.click(screen.getByRole('button', { name: words.player.next }));
    expect(node('Mémoire')).toHaveClass('is-on');

    await user.click(node('Notifications'));
    expect(await screen.findByRole('dialog', { name: 'Notifications' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('button', { name: words.player.next })).not.toBeInTheDocument();
  });

  it('searches a brick and replays its journey from the detail panel', async () => {
    const { user, words } = await renderLanding();
    await user.type(screen.getByRole('searchbox'), 'memoire{Enter}');
    const dialog = await screen.findByRole('dialog', { name: 'Mémoire' });
    expect(window.location.hash).toBe('#f.two');
    await user.click(within(dialog).getByRole('button', { name: 'Une demande' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: words.player.quit })).toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
    expect(window.location.hash).toBe('');
  });
});

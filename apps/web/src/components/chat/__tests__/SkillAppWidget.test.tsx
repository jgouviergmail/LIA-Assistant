/**
 * SkillAppWidget — the registry-item gating (null unless a SKILL_APP item),
 * the image-card rendering, and the frame failure states.
 *
 * The failure states are not cosmetic: before them, an embed the engine
 * refuses (every iOS browser, under `COEP_MODE=require-corp`) rendered a
 * permanently blank rectangle with no message and no log.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useRegistryItem } = vi.hoisted(() => ({ useRegistryItem: vi.fn() }));
vi.mock('@/lib/registry-context', () => ({ useRegistryItem }));

import { SkillAppWidget } from '../SkillAppWidget';

/** Emulate an engine's COEP-relevant capabilities (jsdom exposes neither). */
function setEngine(opts: { isolated: boolean; credentialless: boolean }): void {
  Object.defineProperty(window, 'crossOriginIsolated', {
    value: opts.isolated,
    configurable: true,
    writable: true,
  });
  if (opts.credentialless) {
    Object.defineProperty(HTMLIFrameElement.prototype, 'credentialless', {
      value: false,
      configurable: true,
      writable: true,
    });
  } else {
    delete (HTMLIFrameElement.prototype as unknown as Record<string, unknown>).credentialless;
  }
}

const MAP_ITEM = {
  type: 'SKILL_APP',
  payload: {
    skill_name: 'interactive-map',
    title: 'Map',
    frame_url: 'https://www.google.com/maps/embed?pb=x',
    is_system_skill: true,
  },
};

beforeEach(() => vi.clearAllMocks());

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).crossOriginIsolated;
  delete (HTMLIFrameElement.prototype as unknown as Record<string, unknown>).credentialless;
});

describe('SkillAppWidget', () => {
  it('renders the unavailable placeholder when the registry item is missing', () => {
    useRegistryItem.mockReturnValue(undefined);
    renderWithProviders(<SkillAppWidget registryId="r1" />);
    expect(screen.getByText('skill_apps.error')).toBeInTheDocument();
  });

  it('renders the unavailable placeholder when the item is not a SKILL_APP', () => {
    useRegistryItem.mockReturnValue({ type: 'MCP_APP', payload: {} });
    renderWithProviders(<SkillAppWidget registryId="r1" />);
    expect(screen.getByText('skill_apps.error')).toBeInTheDocument();
  });

  it('renders the image card for a SKILL_APP item with an image', () => {
    useRegistryItem.mockReturnValue({
      type: 'SKILL_APP',
      payload: { image_url: 'https://x/y.png', image_alt: 'A chart' },
    });
    renderWithProviders(<SkillAppWidget registryId="r1" />);
    expect(screen.getByRole('img', { name: 'A chart' })).toHaveAttribute('src', 'https://x/y.png');
  });

  describe('cross-origin frame under COEP', () => {
    it('embeds the frame when the engine supports `credentialless` (Chromium)', () => {
      setEngine({ isolated: true, credentialless: true });
      useRegistryItem.mockReturnValue(MAP_ITEM);
      renderWithProviders(<SkillAppWidget registryId="r1" />);

      const frame = document.querySelector('iframe');
      expect(frame).not.toBeNull();
      expect(frame).toHaveAttribute('src', MAP_ITEM.payload.frame_url);
      // The attribute is what makes the embed work under require-corp.
      expect(frame!.hasAttribute('credentialless')).toBe(true);
      expect(screen.queryByText('skill_apps.frame_unsupported')).toBeNull();
    });

    it('renders an actionable link INSTEAD of a doomed frame on WebKit (isolated, no `credentialless`)', () => {
      setEngine({ isolated: true, credentialless: false });
      useRegistryItem.mockReturnValue(MAP_ITEM);
      renderWithProviders(<SkillAppWidget registryId="r1" />);

      expect(document.querySelector('iframe')).toBeNull();
      expect(screen.getByText('skill_apps.frame_unsupported')).toBeInTheDocument();
      const link = screen.getByRole('link', { name: 'skill_apps.frame_open_external' });
      expect(link).toHaveAttribute('href', MAP_ITEM.payload.frame_url);
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('prefers the user-facing link_url over the embed URL in the fallback', () => {
      // The embed endpoint refuses top-level rendering ("The Google Maps
      // Embed API must be used in an iframe") — handing it to the user as
      // a link is a dead end, which is exactly what link_url exists for.
      setEngine({ isolated: true, credentialless: false });
      useRegistryItem.mockReturnValue({
        ...MAP_ITEM,
        payload: { ...MAP_ITEM.payload, link_url: 'https://www.google.com/maps?q=Paris' },
      });
      renderWithProviders(<SkillAppWidget registryId="r1" />);

      const link = screen.getByRole('link', { name: 'skill_apps.frame_open_external' });
      expect(link).toHaveAttribute('href', 'https://www.google.com/maps?q=Paris');
    });

    it('refuses a NON-system external frame even on Chromium — no `credentialless` attribute is applied', () => {
      // The case rehydration can produce: a widget whose `is_system_skill` was
      // cleared (skill demoted, or the skills cache unavailable). Chromium
      // refuses it too, and there the refusal is invisible — `load` fires on
      // the error document, so the watchdog would never trigger.
      setEngine({ isolated: true, credentialless: true });
      useRegistryItem.mockReturnValue({
        ...MAP_ITEM,
        payload: { ...MAP_ITEM.payload, is_system_skill: false },
      });
      renderWithProviders(<SkillAppWidget registryId="r1" />);

      expect(document.querySelector('iframe')).toBeNull();
      expect(screen.getByText('skill_apps.frame_unsupported')).toBeInTheDocument();
    });

    it('still embeds when the page is not cross-origin isolated (COEP imposes nothing)', () => {
      setEngine({ isolated: false, credentialless: false });
      useRegistryItem.mockReturnValue(MAP_ITEM);
      renderWithProviders(<SkillAppWidget registryId="r1" />);
      expect(document.querySelector('iframe')).not.toBeNull();
    });

    it('never withholds a srcDoc frame — it embeds nothing cross-origin', () => {
      setEngine({ isolated: true, credentialless: false });
      useRegistryItem.mockReturnValue({
        type: 'SKILL_APP',
        payload: { skill_name: 'tic-tac-toe', html_content: '<p>game</p>' },
      });
      renderWithProviders(<SkillAppWidget registryId="r1" />);
      expect(document.querySelector('iframe')).not.toBeNull();
      expect(screen.queryByText('skill_apps.frame_unsupported')).toBeNull();
    });
  });
});

/**
 * Content contract of the two gallery tabs.
 *
 * The carousel's behaviour is covered by LandingCarousel.test.tsx; what is at
 * stake here is what each tab FEEDS it: the full capture inventory, the full
 * deck, distinct names, and the deliberate asymmetry on the full-screen view
 * (captures are dense and light, a deck slide is already served at its
 * readable width and weighs 2 MB).
 *
 * The global i18n stub echoes keys and drops interpolation, which would give
 * the 15 slides one identical name — so this file installs a stub that keeps
 * the variables.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, string | number>) =>
      vars ? `${key}(${Object.values(vars).join(',')})` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));

import { PresentationSection } from '../PresentationSection';
import { ScreenshotsSection } from '../ScreenshotsSection';
import { GallerySection } from '../editorial/GallerySection';
import homeProof from '../../../../public/screenshots/manifest.json';
import applicationProof from '../../../../public/screenshots/proof/manifest.json';
import extendedProof from '../../../../public/screenshots/proof/extended-manifest.json';
import monitoringProof from '../../../../public/screenshots/proof/grafana-manifest.json';
import worldProof from '../../../../public/screenshots/proof/world-manifest.json';

/** Thumbnails are the only per-slide named controls: one per view. */
function thumbnailNames(): string[] {
  return screen
    .getAllByRole('button')
    .map(b => b.getAttribute('aria-label') ?? '')
    .filter(name => !name.startsWith('common.'));
}

describe('ScreenshotsSection', () => {
  it('keeps the application capture revision when opening the full-screen view', async () => {
    const user = userEvent.setup();
    render(<ScreenshotsSection view="dossier" />);
    const src = `/screenshots/proof/dossier.png?v=${applicationProof.revision}`;
    const image = screen.getByRole('img', { name: 'landing.screenshots.proof.dossier' });
    expect(image).toHaveAttribute('src', src);
    expect(image).not.toHaveAttribute('srcset');
    await user.click(screen.getByRole('button', { name: 'common.expand_image' }));
    expect(within(screen.getByRole('dialog')).getByRole('img')).toHaveAttribute('src', src);
  });

  it('uses the monitoring revision for the Grafana images', () => {
    render(<ScreenshotsSection monitoring />);
    const image = screen.getByRole('img', { name: 'landing.screenshots.proof.grafana_overview' });
    expect(image).toHaveAttribute(
      'src',
      `/screenshots/proof/grafana-overview.png?v=${monitoringProof.revision}`
    );
    expect(image).not.toHaveAttribute('srcset');
  });

  it('starts with the personal hub and offers all 32 distinct application views', async () => {
    const user = userEvent.setup();
    render(<ScreenshotsSection />);

    const names = thumbnailNames();
    expect(names).toHaveLength(32);
    expect(new Set(names).size).toBe(32);
    expect(applicationProof.images).toHaveLength(12);
    const extendedImages: { file: string }[] = extendedProof.images;
    expect(extendedImages).toHaveLength(18);
    expect(names[0]).toBe('landing.screenshots.proof.dashboard');
    expect(names[1]).toBe('landing.screenshots.proof.world');
    expect(names[2]).toBe('landing.screenshots.proof.dossier');
    expect(names).toContain('landing.screenshots.proof.radio');
    expect(names).toContain('landing.screenshots.proof.relations');
    expect(names).toContain('landing.screenshots.proof.meetings');
    expect(names).toEqual(
      expect.arrayContaining(
        applicationProof.images.map(
          image => `landing.screenshots.proof.${image.file.replace('.png', '')}`
        )
      )
    );
    expect(names).toEqual(
      expect.arrayContaining(
        extendedImages.map(
          image =>
            `landing.screenshots.proof.${image.file.replace('.png', '').replaceAll('-', '_')}`
        )
      )
    );
    expect(names).not.toContain('landing.screenshots.proof.grafana_overview');
    const src = `/screenshots/dashboard-wide.png?v=${homeProof.revision}`;
    const image = screen.getByRole('img', { name: names[0] });
    expect(image).toHaveAttribute('src', src);
    expect(image).not.toHaveAttribute('srcset');
    // The gallery uses the readable viewport capture and preserves its source in full screen.
    await user.click(screen.getByRole('button', { name: 'common.expand_image' }));
    expect(within(screen.getByRole('dialog')).getByRole('img')).toHaveAttribute('src', src);
  });

  it('opens the owner-supplied world JPEG at its original revision in full screen', async () => {
    const user = userEvent.setup();
    render(<ScreenshotsSection view="world" />);
    const src = `/screenshots/proof/lia-world.jpg?v=${worldProof.revision}`;
    expect(screen.getByRole('img', { name: 'landing.screenshots.proof.world' })).toHaveAttribute(
      'src',
      src
    );
    expect(worldProof.images[0]).toMatchObject({ width: 2054, height: 1038 });
    await user.click(screen.getByRole('button', { name: 'common.expand_image' }));
    expect(within(screen.getByRole('dialog')).getByRole('img')).toHaveAttribute('src', src);
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'common.expand_image' })).toHaveFocus();
  });

  it('reaches the added application views by keyboard and keeps their campaign revision in full screen', async () => {
    const user = userEvent.setup();
    render(<ScreenshotsSection />);

    const carousel = screen.getByRole('group', { name: 'landing.gallery.tab_screens' });
    carousel.focus();
    await user.keyboard('{End}');

    const src = `/screenshots/proof/journal.png?v=${extendedProof.revision}`;
    expect(screen.getByRole('img', { name: 'landing.screenshots.proof.journal' })).toHaveAttribute(
      'src',
      src
    );
    expect(
      screen.getByRole('button', { name: 'landing.screenshots.proof.journal' })
    ).toHaveAttribute('aria-current', 'true');
    await user.click(screen.getByRole('button', { name: 'common.expand_image' }));
    expect(within(screen.getByRole('dialog')).getByRole('img')).toHaveAttribute('src', src);
  });

  it('offers full-screen inspection of application and monitoring captures', () => {
    render(<ScreenshotsSection />);
    expect(screen.getByRole('button', { name: 'common.expand_image' })).toBeInTheDocument();
  });

  it('lets an operator inspect the three dedicated monitoring views', async () => {
    const user = userEvent.setup();
    render(<ScreenshotsSection monitoring />);

    expect(thumbnailNames()).toEqual([
      'landing.screenshots.proof.grafana_overview',
      'landing.screenshots.proof.grafana_costs',
      'landing.screenshots.proof.grafana_activity',
    ]);
    expect(
      screen.getByRole('group', { name: 'landing.platform.dashboard_title' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: 'landing.screenshots.proof.grafana_overview' })
    ).toBeVisible();
    const costs = screen.getByRole('button', { name: 'landing.screenshots.proof.grafana_costs' });
    await user.click(costs);
    expect(costs).toHaveFocus();
    expect(costs).toHaveAttribute('aria-current', 'true');
    expect(
      screen.getByRole('img', { name: 'landing.screenshots.proof.grafana_costs' })
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'common.expand_image' })).toBeVisible();
    const activity = screen.getByRole('button', {
      name: 'landing.screenshots.proof.grafana_activity',
    });
    activity.focus();
    await user.keyboard('{Enter}');
    expect(activity).toHaveFocus();
    expect(activity).toHaveAttribute('aria-current', 'true');
    const src = `/screenshots/proof/grafana-activity.png?v=${monitoringProof.revision}`;
    expect(
      screen.getByRole('img', { name: 'landing.screenshots.proof.grafana_activity' })
    ).toHaveAttribute('src', src);
    await user.click(screen.getByRole('button', { name: 'common.expand_image' }));
    expect(within(screen.getByRole('dialog')).getByRole('img')).toHaveAttribute('src', src);
  });
});

describe('GallerySection', () => {
  it('starts with application screenshots and lets the keyboard switch to the presentation', async () => {
    const user = userEvent.setup();
    render(<GallerySection />);

    const screens = screen.getByRole('tab', { name: 'landing.gallery.tab_screens' });
    const slides = screen.getByRole('tab', { name: 'landing.gallery.tab_slides' });
    expect(screens).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'landing.gallery.tab_screens' })).toBeVisible();
    expect(screen.getByRole('img', { name: 'landing.screenshots.proof.dashboard' })).toBeVisible();
    expect(screen.getByText('landing.gallery.provenance')).toBeVisible();
    expect(screen.getByRole('button', { name: 'common.expand_image' })).toBeVisible();

    screens.focus();
    await user.keyboard('{ArrowRight}');
    expect(slides).toHaveFocus();
    expect(slides).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'landing.gallery.tab_slides' })).toBeVisible();
    expect(screen.getByRole('img', { name: 'landing.presentation.slide_alt(1)' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'common.expand_image' })).not.toBeInTheDocument();
  });
});

describe('PresentationSection', () => {
  it('feeds the carousel the 15 slides in order', () => {
    render(<PresentationSection />);

    const names = thumbnailNames();
    expect(names).toHaveLength(15);
    expect(names[0]).toBe('landing.presentation.slide_alt(1)');
    expect(names[14]).toBe('landing.presentation.slide_alt(15)');
  });

  it('captions each slide with its position — the deck has no other title', () => {
    const { container } = render(<PresentationSection />);
    expect(container.querySelector('[aria-live="polite"]')).toHaveTextContent(
      'landing.presentation.slide_counter(1,15)'
    );
  });

  it('does not offer the full-screen view (a slide is a 2 MB asset)', () => {
    render(<PresentationSection />);
    expect(screen.queryByRole('button', { name: 'common.expand_image' })).toBeNull();
  });
});

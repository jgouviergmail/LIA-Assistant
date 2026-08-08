/**
 * Composition contract of the public landing (`/[lng]`), which carries the
 * cosmos identity since the swap: every real section present in the real
 * order inside the `.cosmos` scope, the production contract restored versus
 * the old preview (AuthRedirect, TrackView, JSON-LD, full SEO metadata), and
 * no preview tooling left behind.
 *
 * Heavy server sections are mocked to lightweight markers: this test's oracle
 * is the composition, not the sections' internals (each has its own tests).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Server sections → synchronous markers (the page awaits them as RSC).
vi.mock('@/components/seo/JsonLd', () => ({
  SoftwareApplicationJsonLd: () => <div data-testid="jsonld-software" />,
  HowToJsonLd: () => <div data-testid="jsonld-howto" />,
}));
vi.mock('@/components/landing/AuthRedirect', () => ({
  AuthRedirect: () => <div data-testid="auth-redirect" />,
}));
vi.mock('@/components/telemetry/TelemetryBootstrap', () => ({
  TrackView: ({ event }: { event: string }) => <div data-testid="track-view" data-event={event} />,
}));
vi.mock('@/components/landing/LandingHeader', () => ({
  LandingHeader: () => <div data-testid="landing-header" />,
}));
vi.mock('@/components/landing/editorial/EditorialChapters', () => ({
  EditorialChapters: ({ ghosts }: { ghosts?: boolean }) => (
    <div data-testid="editorial-chapters" data-ghosts={String(ghosts)} />
  ),
}));
vi.mock('@/components/landing/editorial/BasicsBand', () => ({
  BasicsBand: () => <div data-testid="basics-band" />,
}));
vi.mock('@/components/landing/editorial/TransparencySection', () => ({
  TransparencySection: ({ ghost }: { ghost?: React.ReactNode }) => (
    <div data-testid="transparency-section">{ghost}</div>
  ),
}));
vi.mock('@/components/landing/editorial/GallerySection', () => ({
  GallerySection: () => <div data-testid="gallery-section" />,
}));
vi.mock('@/components/landing/UseCasesSection', () => ({
  UseCasesSection: () => <div data-testid="usecases-section" />,
}));
vi.mock('@/components/landing/TechSection', () => ({
  TechSection: () => <div data-testid="tech-section" />,
}));
vi.mock('@/components/landing/ArchitectureDiagram', () => ({
  ArchitectureDiagram: () => <div data-testid="architecture-diagram" />,
}));
vi.mock('@/components/landing/BlogPreviewSection', () => ({
  BlogPreviewSection: () => <div data-testid="blog-preview" />,
}));
vi.mock('@/components/landing/LandingFooter', () => ({
  LandingFooter: () => <div data-testid="landing-footer" />,
}));
vi.mock('@/components/landing/cosmic/CosmosHero', () => ({
  CosmosHero: () => <div data-testid="cosmos-hero" />,
}));

import HomePage, { generateMetadata } from '../page';

const PARAMS = { params: Promise.resolve({ lng: 'fr' }) };

describe('HomePage (cosmos landing)', () => {
  it('composes every real landing section, in the real order, inside .cosmos', async () => {
    const { container } = render(await HomePage(PARAMS));

    expect(container.querySelector('.landing-page.cosmos')).toBeInTheDocument();
    expect(screen.getByTestId('cosmic-backdrop')).toBeInTheDocument();

    const order = [
      'landing-header',
      'cosmos-hero',
      'editorial-chapters',
      'basics-band',
      'transparency-section',
      'usecases-section',
      'gallery-section',
      'tech-section',
      'architecture-diagram',
      'blog-preview',
      'landing-footer',
    ];
    const positions = order.map(id => {
      const el = screen.getByTestId(id);
      return Array.prototype.indexOf.call(container.querySelectorAll('[data-testid]'), el);
    });
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);

    // Ghost words: chapters get theirs via the additive prop, transparency
    // receives an explicit GhostWord node.
    expect(screen.getByTestId('editorial-chapters')).toHaveAttribute('data-ghosts', 'true');
    expect(
      screen.getByTestId('transparency-section').querySelector('.cosmos-ghost')
    ).toHaveTextContent('landing.cosmos.ghost.transparency');

    // The pinned day and the finale render live (not mocked).
    expect(screen.getByRole('heading', { name: 'landing.day.title' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'landing.cta.title' })).toBeInTheDocument();
    // Finale horizon: clean planet — clouds only (no lightning, dawn, rim, moonlet).
    expect(container.querySelector('.cosmos-globe')).toBeInTheDocument();
    expect(container.querySelectorAll('.cosmos-cloud')).toHaveLength(3);
    expect(container.querySelector('.cosmos-lightning')).not.toBeInTheDocument();
    expect(container.querySelector('.cosmos-dawn')).not.toBeInTheDocument();
    expect(container.querySelector('.cosmos-rim')).not.toBeInTheDocument();
    expect(container.querySelector('.cosmos-moonlet')).not.toBeInTheDocument();
  });

  it('restores the production contract the preview deliberately dropped', async () => {
    const { container } = render(await HomePage(PARAMS));

    // Authenticated visitors bounce to the dashboard again.
    expect(screen.getByTestId('auth-redirect')).toBeInTheDocument();
    // ADR-178 product funnel measures the landing again.
    expect(screen.getByTestId('track-view')).toHaveAttribute('data-event', 'landing_view');
    // SEO structured data present.
    expect(screen.getByTestId('jsonld-software')).toBeInTheDocument();
    expect(screen.getByTestId('jsonld-howto')).toBeInTheDocument();
    // No preview tooling chrome survives the swap.
    expect(container.querySelector('nav[aria-label="Prévisualisations Cosmos"]')).toBeNull();
  });

  it('serves indexable SEO metadata (canonical + hreflang, no noindex)', async () => {
    // The origin is STUBBED, never read from the ambient environment. Since
    // the release image became host-neutral (ADR-215/B03), no hardcoded
    // fallback origin survives in the code: an unset variable yields RELATIVE
    // URLs. A test that reads `process.env.NEXT_PUBLIC_APP_URL || '<a domain>'`
    // therefore asserted the OLD behaviour and passed locally only because the
    // Taskfile's global `dotenv: .env` injects the dev value — it failed in CI,
    // which has no such environment.
    const base = 'https://lia.test';
    vi.stubEnv('NEXT_PUBLIC_APP_URL', base);
    vi.stubEnv('APP_URL_SERVER', '');
    const metadata = await generateMetadata(PARAMS);
    expect(metadata.robots).toBeUndefined();
    expect(metadata.alternates?.canonical).toBe(`${base}/`);
    expect(metadata.alternates?.languages).toMatchObject({
      fr: `${base}/`,
      en: `${base}/en/`,
      'x-default': `${base}/`,
    });
    expect(metadata.title).toBeTruthy();
    vi.unstubAllEnvs();
  });

  it('falls back to RELATIVE canonicals when no origin is configured', async () => {
    // The host-neutral release image ships without an origin: the page must
    // degrade to relative URLs rather than invent a domain. Absence is stubbed
    // EXPLICITLY — relying on it being ambiently absent passes in CI and fails
    // under `task test:frontend`, which inherits the dev `.env`.
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '');
    vi.stubEnv('APP_URL_SERVER', '');
    const metadata = await generateMetadata(PARAMS);

    expect(metadata.alternates?.canonical).toBe('/');
    expect(metadata.alternates?.languages).toMatchObject({
      fr: '/',
      en: '/en/',
      'x-default': '/',
    });
    vi.unstubAllEnvs();
  });
});

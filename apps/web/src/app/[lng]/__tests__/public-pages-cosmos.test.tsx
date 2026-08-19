/**
 * The public space wears the cosmos identity since the swap: `/more` and
 * `/demo` carry the full scope, every reading page (story, why, how, faq,
 * blog index + article, privacy, terms) carries the CALM sub-scope, and none
 * of them is dev-gated (they are the real routes, indexable in production).
 *
 * Real content components are mocked to markers — each page's content has its
 * own tests; the oracle here is the scope + composition per page TYPE.
 */

import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/seo/JsonLd', async importOriginal => ({
  // serializeJsonLd stays real (pure helper used by blog metadata).
  ...(await importOriginal<typeof import('@/components/seo/JsonLd')>()),
  BreadcrumbJsonLd: () => <div data-testid="jsonld-breadcrumb" />,
  BlogListJsonLd: () => <div data-testid="jsonld-bloglist" />,
  FAQPageJsonLd: () => <div data-testid="jsonld-faq" />,
}));
vi.mock('@/components/landing/LandingHeader', () => ({
  LandingHeader: () => <div data-testid="landing-header" />,
}));
vi.mock('@/components/landing/more/MoreContent', () => ({
  MoreContent: () => <div data-testid="more-content" />,
}));
vi.mock('@/components/guides/StoryContent', () => ({
  StoryContent: () => <div data-testid="story-content" />,
}));
vi.mock('@/components/guides/WhyContent', () => ({
  WhyContent: () => <div data-testid="why-content" />,
}));
vi.mock('@/components/guides/HowContent', () => ({
  HowContent: () => <div data-testid="how-content" />,
}));
vi.mock('@/components/faq/PublicFAQContent', () => ({
  PublicFAQContent: () => <div data-testid="faq-content" />,
}));
vi.mock('@/components/changelog/ChangelogHistory', () => ({
  ChangelogHistory: () => <div data-testid="changelog-history" />,
}));
vi.mock('@/components/blog/BlogCard', () => ({
  BlogCard: () => <div data-testid="blog-card" />,
}));
vi.mock('@/components/blog/BlogArticleContent', () => ({
  BlogArticleContent: () => <div data-testid="blog-article" />,
}));
vi.mock('@/components/legal/PrivacyContent', () => ({
  PrivacyContent: () => <div data-testid="privacy-content" />,
}));
vi.mock('@/components/legal/TermsContent', () => ({
  TermsContent: () => <div data-testid="terms-content" />,
}));
vi.mock('@/components/LanguageSelector', () => ({
  LanguageSelector: () => <div data-testid="language-selector" />,
}));
vi.mock('@/components/theme-toggle', () => ({
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}));
vi.mock('@/components/layout/PublicFooter', () => ({
  PublicFooter: () => <div data-testid="public-footer" />,
}));
vi.mock('@/components/landing/InteractiveChatMockup', () => ({
  InteractiveChatMockup: () => <div data-testid="chat-mockup" />,
}));
vi.mock('@/components/telemetry/TelemetryBootstrap', () => ({
  TrackView: ({ event }: { event: string }) => <div data-testid="track-view" data-event={event} />,
}));
vi.mock('@/components/showroom/GuidedShowroom', () => ({
  GuidedShowroom: () => <div data-testid="guided-showroom" />,
}));
vi.mock('@/lib/showroom-config', () => ({
  getPublicShowroomVariant: vi.fn(() => 'legacy'),
  // Dedicated live flag: OFF here — the guided/legacy contract under test
  // must never depend on the live deployment decision.
}));

import { getPublicShowroomVariant } from '@/lib/showroom-config';

const variantMock = vi.mocked(getPublicShowroomVariant);

import { BLOG_ARTICLES } from '@/data/blog-articles';
import BlogArticlePage from '../blog/[slug]/page';
import BlogPage from '../blog/page';
import ChangelogPage from '../changelog/page';
import DemoPage from '../demo/page';
import FaqPage from '../faq/page';
import HowPage from '../how/page';
import MorePage from '../more/page';
import PrivacyPage from '../privacy/page';
import StoryPage from '../story/page';
import TermsPage from '../terms/page';
import WhyPage from '../why/page';

const PARAMS = { params: Promise.resolve({ lng: 'fr' }) };

describe('public pages — cosmos identity', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('/more wraps the real MoreContent in the full cosmos scope', async () => {
    const { container, getByTestId } = render(await MorePage(PARAMS));
    expect(container.querySelector('.landing-page.cosmos')).toBeInTheDocument();
    expect(container.querySelector('.cosmos-calm')).not.toBeInTheDocument();
    expect(getByTestId('more-content')).toBeInTheDocument();
    expect(getByTestId('cosmic-backdrop')).toBeInTheDocument();
    expect(getByTestId('public-footer')).toBeInTheDocument();
    expect(getByTestId('jsonld-breadcrumb')).toBeInTheDocument();
  });

  it('/demo centers the real mockup inside the planetarium and keeps its funnel event', async () => {
    const { container, getByTestId } = render(await DemoPage(PARAMS));
    expect(container.querySelector('.landing-page.cosmos')).toBeInTheDocument();
    expect(getByTestId('chat-mockup')).toBeInTheDocument();
    expect(getByTestId('planetarium')).toBeInTheDocument();
    expect(getByTestId('track-view')).toHaveAttribute('data-event', 'demo_started');
  });

  it('/demo guided renders ONLY the mission — never TrackView or the mockup', async () => {
    variantMock.mockReturnValueOnce('guided');
    const { container, getByTestId, queryByTestId } = render(await DemoPage(PARAMS));
    // Cosmos shell preserved in both branches.
    expect(container.querySelector('.landing-page.cosmos')).toBeInTheDocument();
    expect(getByTestId('guided-showroom')).toBeInTheDocument();
    // The guided branch must never mount the credentialed TrackView emitter,
    // nor the legacy mockup/planetarium composition.
    expect(queryByTestId('track-view')).not.toBeInTheDocument();
    expect(queryByTestId('chat-mockup')).not.toBeInTheDocument();
    expect(queryByTestId('planetarium')).not.toBeInTheDocument();
  });

  it.each([
    ['story', StoryPage, 'story-content'],
    ['why', WhyPage, 'why-content'],
    ['how', HowPage, 'how-content'],
    ['faq', FaqPage, 'faq-content'],
    ['changelog', ChangelogPage, 'changelog-history'],
    ['blog', BlogPage, 'jsonld-bloglist'],
    ['privacy', PrivacyPage, 'privacy-content'],
    ['terms', TermsPage, 'terms-content'],
  ])('/%s applies the CALM sub-scope to its real content', async (_n, Page, marker) => {
    const { container, getByTestId } = render(await Page(PARAMS));
    expect(container.querySelector('.cosmos.cosmos-calm')).toBeInTheDocument();
    expect(getByTestId(marker)).toBeInTheDocument();
    expect(getByTestId('cosmic-backdrop')).toBeInTheDocument();
    // Calm doctrine: no ghost word, no pinned scene on reading surfaces.
    expect(container.querySelector('.cosmos-ghost-frame')).not.toBeInTheDocument();
    expect(container.querySelector('.cosmos-pin-stage')).not.toBeInTheDocument();
  });

  it('/blog/[slug] applies the CALM sub-scope to a real article', async () => {
    const slug = BLOG_ARTICLES[0].slug;
    const { container, getByTestId } = render(
      await BlogArticlePage({ params: Promise.resolve({ lng: 'fr', slug }) })
    );
    expect(container.querySelector('.cosmos.cosmos-calm')).toBeInTheDocument();
    expect(getByTestId('blog-article')).toBeInTheDocument();
  });

  it.each([
    ['more', MorePage],
    ['demo', DemoPage],
    ['story', StoryPage],
    ['faq', FaqPage],
    ['changelog', ChangelogPage],
  ])('/%s is NOT dev-gated (real route, renders in production)', async (_n, Page) => {
    vi.stubEnv('NODE_ENV', 'production');
    const { container } = render(await Page(PARAMS));
    expect(container.querySelector('.cosmos')).toBeInTheDocument();
  });
});

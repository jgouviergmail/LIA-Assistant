/**
 * MarkdownContent — the component dispatch behind the markdown pipeline.
 * (XSS sanitisation lives in `MarkdownContent.sanitize.test.tsx`, maths in
 * `MarkdownContent.math.test.tsx`.)
 *
 * The assistant emits *sentinel* markup — `<div class="lia-mcp-app"
 * data-registry-id=…>`, `<div class="lia-place__photo" data-photo-urls=…>`,
 * widgets. Three properties matter:
 *
 *  - a sentinel **missing its payload** must degrade to a plain container
 *    rather than mounting a widget with nothing to show;
 *  - malformed sentinel data (the LLM writes it) must never break the message —
 *    a broken photo list costs a carousel, not the answer;
 *  - images are classified (LIA component / place photo / plain) and their
 *    loaded state is cached, so a re-render during streaming does not make the
 *    picture flash back to transparent.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, fireEvent } from '@/__tests__/test-utils';

const { markImageLoaded, isImageLoaded } = vi.hoisted(() => ({
  markImageLoaded: vi.fn(),
  isImageLoaded: vi.fn(() => false),
}));
vi.mock('@/lib/image-cache', () => ({ markImageLoaded, isImageLoaded }));

// The two sentinel widgets are lazy-loaded units with their own suites; they
// are stubbed so this file tests the dispatch, not their internals.
vi.mock('@/components/chat/McpAppWidget', () => ({
  McpAppWidget: ({ registryId }: { registryId: string }) => (
    <div data-testid="mcp-widget">{registryId}</div>
  ),
}));
vi.mock('@/components/chat/SkillAppWidget', () => ({
  SkillAppWidget: ({ registryId }: { registryId: string }) => (
    <div data-testid="skill-widget">{registryId}</div>
  ),
}));

import { MarkdownContent } from '../MarkdownContent';

const render = (content: string) => renderWithProviders(<MarkdownContent content={content} />);

const PLACE_PHOTO = 'https://api.example.com/api/v1/connectors/google-places/photo?ref=abc';

beforeEach(() => {
  vi.clearAllMocks();
  isImageLoaded.mockReturnValue(false);
});

describe('MarkdownContent — sentinel dispatch', () => {
  it('turns a reasoning block into its own scrolling container', () => {
    const { container } = render('<div class="lia-reasoning">Je réfléchis…</div>');

    expect(screen.getByText('Je réfléchis…')).toBeInTheDocument();
    // ReasoningScroll keeps `lia-reasoning` (it is its own styling hook) and
    // adds the bounded scroll box. That box has no ARIA identity, so in jsdom
    // its class is the only observable that tells the dispatch apart from the
    // default `<div className={className}>` branch — which would render the
    // original class alone and let the streamed thoughts push the page down.
    const block = container.querySelector('div.lia-reasoning');
    expect(block?.className).toContain('overflow-y-auto');
  });

  it('mounts the MCP widget for its registry id', async () => {
    render('<div class="lia-mcp-app" data-registry-id="app-42"></div>');

    expect(await screen.findByTestId('mcp-widget')).toHaveTextContent('app-42');
  });

  it('mounts the skill widget for its registry id', async () => {
    render('<div class="lia-skill-app" data-registry-id="skill-7"></div>');

    expect(await screen.findByTestId('skill-widget')).toHaveTextContent('skill-7');
  });

  it.each([
    ['lia-mcp-app', 'mcp-widget'],
    ['lia-skill-app', 'skill-widget'],
  ])('renders %s without its registry id as a plain container', async (className, testId) => {
    const { container } = render(`<div class="${className}">contenu de repli</div>`);

    expect(screen.getByText('contenu de repli')).toBeInTheDocument();
    expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
    expect(container.querySelector(`div.${className}`)).not.toBeNull();
  });

  it('keeps an ordinary div as an ordinary div', () => {
    const { container } = render('<div class="whatever">texte</div>');

    expect(container.querySelector('div.whatever')).not.toBeNull();
    expect(screen.getByText('texte')).toBeInTheDocument();
  });
});

describe('MarkdownContent — place photos', () => {
  it('turns several photos into a carousel', () => {
    const urls = JSON.stringify([PLACE_PHOTO, `${PLACE_PHOTO}&i=2`]);
    render(
      `<div class="lia-place__photo" data-photo-urls='${urls}'><img src="${PLACE_PHOTO}"></div>`
    );

    // The carousel exposes navigation; a single image never would.
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0);
  });

  it('leaves a single photo as it was', () => {
    const urls = JSON.stringify([PLACE_PHOTO]);
    const { container } = render(
      `<div class="lia-place__photo" data-photo-urls='${urls}'><img src="${PLACE_PHOTO}" alt="La terrasse"></div>`
    );

    expect(container.querySelector('img[alt="La terrasse"]')).not.toBeNull();
  });

  it('survives a photo list the model wrote badly', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(
      `<div class="lia-place__photo" data-photo-urls='{not json'><img src="${PLACE_PHOTO}" alt="La terrasse"></div>`
    );

    // The answer must survive a broken photo list: it costs a carousel, not
    // the message.
    expect(container.querySelector('img[alt="La terrasse"]')).not.toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('renders the wrapper even with no photo data at all', () => {
    const { container } = render('<div class="lia-place__photo">Sans photo</div>');

    expect(container.querySelector('div.lia-place__photo')).not.toBeNull();
    expect(screen.getByText('Sans photo')).toBeInTheDocument();
  });
});

describe('MarkdownContent — standalone images', () => {
  it('renders a LIA component image untouched, keeping its class', () => {
    const { container } = render(
      '<img src="https://cdn.example.com/c.png" class="lia-card__image" alt="Carte">'
    );

    const img = container.querySelector('img.lia-card__image');
    expect(img).not.toBeNull();
    // No lightbox wrapper: it would break the card's flex layout.
    expect(img?.closest('button')).toBeNull();
  });

  it('makes a place photo openable', () => {
    const { container } = render(`<img src="${PLACE_PHOTO}" alt="Le café">`);

    const img = container.querySelector('img[alt="Le café"]');
    expect(img).not.toBeNull();
    expect(img?.closest('button')).not.toBeNull();
  });

  it('marks a plain image as loaded once it arrives', () => {
    const { container } = render('<img src="https://cdn.example.com/d.png" alt="Photo">');
    const img = container.querySelector('img[alt="Photo"]');
    expect(img).not.toBeNull();

    fireEvent.load(img!);

    expect(markImageLoaded).toHaveBeenCalledWith('https://cdn.example.com/d.png');
  });
});

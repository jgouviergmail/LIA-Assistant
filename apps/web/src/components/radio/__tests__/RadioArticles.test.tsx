/**
 * The articles a session cited, under the programme (ADR-324): folded, an
 * article costs nothing and asks nothing; opened, it is read whole in the
 * listener's language — translated when its feed speaks another — and what
 * the page shows says what it is: the outlet's summary alone, a cut, a
 * translation that could not be made, and what the reading cost.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { RADIO_ARTICLE_TIMEOUT_MS } from '@/lib/constants';
import type { RadioArticleRef } from '@/lib/radio/articles';
import type { RadioArticle } from '@/lib/radio/types';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

// The global stub echoes the key alone: here the parameters are echoed too, so
// the language named and the cost said can be read back.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

import { RadioArticles } from '../RadioArticles';

const RAIN: RadioArticleRef = {
  id: 'story-rain',
  outlet: 'Example News',
  url: 'https://news.example/rain',
  publishedAt: '2026-09-26T08:00:00Z',
};
const PORT: RadioArticleRef = {
  id: 'story-port',
  outlet: 'Harbour Daily',
  url: 'javascript:alert(1)',
  publishedAt: null,
};

function article(over: Partial<RadioArticle> = {}): RadioArticle {
  return {
    id: RAIN.id,
    outlet: RAIN.outlet,
    url: 'https://news.example/rain',
    published_at: '2026-09-26T08:00:00Z',
    title: 'De la pluie sur la capitale',
    text: 'Premier paragraphe.\n\nSecond paragraphe.',
    complete: true,
    cut: false,
    translated: true,
    source_language: 'de',
    translation_failed: false,
    budget_reached: false,
    cost_eur: 0.0021,
    ...over,
  };
}

beforeEach(() => {
  api.get.mockReset();
});

describe('RadioArticles', () => {
  it('shows nothing before the programme cites a story', () => {
    const { container } = renderWithProviders(<RadioArticles lng="en" articles={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('lists each article folded, and asks nothing for an article nobody opened', () => {
    renderWithProviders(<RadioArticles lng="en" articles={[RAIN, PORT]} />);
    expect(
      screen.getByRole('heading', { name: 'radio.article.section_title' })
    ).toBeInTheDocument();
    expect(screen.getByText('Example News')).toBeInTheDocument();
    expect(screen.getByText('Harbour Daily')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('offers the original while folded, and following it translates nothing', async () => {
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN, PORT]} />);
    const link = screen.getByRole('link', {
      name: 'radio.article.original_label {"outlet":"Example News"}',
    });
    expect(link).toHaveAttribute('href', 'https://news.example/rain');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveTextContent('radio.article.original');
    // An address that is not a web one is never a link, folded or not.
    expect(screen.getAllByRole('link')).toHaveLength(1);

    await user.click(link);
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('reads an opened article whole, in the listener’s language, and says what it cost', async () => {
    api.get.mockResolvedValue(article());
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);

    await user.click(screen.getByText('Example News'));

    expect(api.get).toHaveBeenCalledWith(
      '/radio/articles/story-rain',
      expect.objectContaining({ timeout: RADIO_ARTICLE_TIMEOUT_MS })
    );
    const opened = await screen.findByRole('article', { name: 'De la pluie sur la capitale' });
    expect(within(opened).getByText('Premier paragraphe.')).toBeInTheDocument();
    expect(within(opened).getByText('Second paragraphe.')).toBeInTheDocument();
    expect(
      within(opened).getByText('radio.article.translated {"language":"German"}')
    ).toBeInTheDocument();
    expect(within(opened).getByText(/^radio\.article\.cost /)).toHaveTextContent('0.0021');
    const link = within(opened).getByRole('link', { name: /radio\.article\.read_original/ });
    expect(link).toHaveAttribute('href', 'https://news.example/rain');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('says it is waiting while the article is read and translated', async () => {
    api.get.mockReturnValue(new Promise(() => undefined));
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    expect(await screen.findByRole('status')).toHaveTextContent('radio.article.loading');
  });

  it('says when the page holds the outlet’s summary alone, or a cut article', async () => {
    api.get.mockResolvedValue(article({ complete: false, cut: true }));
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    expect(await screen.findByText('radio.article.summary_only')).toBeInTheDocument();
    expect(screen.getByText('radio.article.cut')).toBeInTheDocument();
  });

  it('shows the original, said so, when the translation could not be made — and what it cost', async () => {
    api.get.mockResolvedValue(
      article({ title: 'Rain over the capital', translated: false, translation_failed: true })
    );
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    expect(await screen.findByText('radio.article.translation_failed')).toBeInTheDocument();
    expect(screen.queryByText(/^radio\.article\.translated/)).not.toBeInTheDocument();
    expect(screen.getByText(/^radio\.article\.cost /)).toBeInTheDocument();
  });

  it('shows the original past the radio’s budget, said so — never as a failure', async () => {
    api.get.mockResolvedValue(
      article({ translated: false, budget_reached: true, cost_eur: 0, title: 'Rain' })
    );
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    expect(await screen.findByText('radio.article.budget_reached')).toBeInTheDocument();
    expect(screen.queryByText('radio.article.translation_failed')).not.toBeInTheDocument();
    expect(screen.queryByText(/^radio\.article\.cost/)).not.toBeInTheDocument();
  });

  it('says nothing of a cost when nothing was translated', async () => {
    api.get.mockResolvedValue(article({ translated: false, source_language: 'en', cost_eur: 0 }));
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    await screen.findByRole('article');
    expect(screen.queryByText(/^radio\.article\.cost/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^radio\.article\.translated/)).not.toBeInTheDocument();
  });

  it('names no language a feed did not declare', async () => {
    api.get.mockResolvedValue(article({ source_language: null }));
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    expect(await screen.findByText('radio.article.translated_unknown')).toBeInTheDocument();
  });

  it('never makes a link of an address that is not a web one', async () => {
    api.get.mockResolvedValue(article({ url: 'javascript:alert(1)' }));
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    const opened = await screen.findByRole('article');
    expect(within(opened).queryByRole('link')).not.toBeInTheDocument();
  });

  it('says an article could not be read, and reads it again on request', async () => {
    api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(article());
    const { user } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('radio.article.error');
    await user.click(within(alert).getByRole('button', { name: 'common.retry' }));

    expect(
      await screen.findByRole('article', { name: 'De la pluie sur la capitale' })
    ).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('keeps an opened article open while the programme cites new ones', async () => {
    api.get.mockResolvedValue(article());
    const { user, rerender } = renderWithProviders(<RadioArticles lng="en" articles={[RAIN]} />);
    await user.click(screen.getByText('Example News'));
    await screen.findByRole('article');

    rerender(<RadioArticles lng="en" articles={[RAIN, PORT]} />);

    expect(
      screen.getByRole('article', { name: 'De la pluie sur la capitale' })
    ).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
  });
});

/**
 * The illustration is a plain <img> over pre-generated variants: what a
 * browser is told (candidates, sizes, loading priority) is the oracle.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ArticleIllustration } from '../ArticleIllustration';

describe('ArticleIllustration', () => {
  it('offers every width as a candidate and defers an off-screen card', () => {
    render(
      <ArticleIllustration
        slug="sub-agents"
        alt="Sub-agents"
        sizes="(max-width: 640px) 100vw, 300px"
      />
    );
    const img = screen.getByRole('img', { name: 'Sub-agents' });
    expect(img).toHaveAttribute('src', '/articles/sub-agents-1024.webp');
    expect(img).toHaveAttribute(
      'srcset',
      '/articles/sub-agents-480.webp 480w, /articles/sub-agents-768.webp 768w, /articles/sub-agents-1024.webp 1024w, /articles/sub-agents-1536.webp 1536w'
    );
    expect(img).toHaveAttribute('sizes', '(max-width: 640px) 100vw, 300px');
    expect(img).toHaveAttribute('loading', 'lazy');
    expect(img).toHaveAttribute('decoding', 'async');
    expect(img).not.toHaveAttribute('fetchpriority');
  });

  it('loads an above-the-fold illustration eagerly and first', () => {
    render(<ArticleIllustration slug="sub-agents" alt="Sub-agents" sizes="768px" priority />);
    const img = screen.getByRole('img', { name: 'Sub-agents' });
    expect(img).toHaveAttribute('loading', 'eager');
    expect(img).toHaveAttribute('fetchpriority', 'high');
  });

  it('keeps the caller in charge of the frame it fills', () => {
    render(
      <ArticleIllustration slug="x" alt="X" sizes="300px" className="object-cover size-full" />
    );
    expect(screen.getByRole('img', { name: 'X' })).toHaveClass('object-cover', 'size-full');
  });
});

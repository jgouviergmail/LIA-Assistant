/**
 * A count shown to the reader is a claim: exact, or absent. The catalog hints
 * ("N detailed capabilities") used to be typed by hand and drifted on every
 * card added — measured 2026-09-17: five of six chapters stated a wrong count.
 * The number now comes from the catalog itself; the copy only carries the
 * `{{count}}` placeholder.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BasicsBand } from '../BasicsBand';
import { ChapterSection } from '../ChapterSection';
import { BASICS_CATALOG, CHAPTERS } from '../chapters-data';

describe('catalog hints derive their count from the catalog', () => {
  it.each(CHAPTERS.map(c => [c.key, c] as const))(
    'chapter %s asks its hint with the catalog length',
    (_key, chapter) => {
      const t = vi.fn((key: string, options?: Record<string, unknown>) =>
        typeof options?.count === 'number' ? `${options.count} cards` : key
      );
      render(<ChapterSection t={t} chapter={chapter} reverse={false} visual={null} />);
      expect(screen.getByText(`${chapter.catalog.length} cards`)).toBeInTheDocument();
      expect(t).toHaveBeenCalledWith(`landing.chapters.${chapter.key}.catalog_hint`, {
        count: chapter.catalog.length,
      });
    }
  );

  it('the basics band states the length of its own catalog', async () => {
    render(await BasicsBand({ lng: 'en' }));
    expect(
      screen.getByText(`${BASICS_CATALOG.length} detailed capabilities`)
    ).toBeInTheDocument();
  });
});

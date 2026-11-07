import type { ReactNode } from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ChapterConfig } from '../chapters-data';

vi.mock('@/i18n', () => ({
  initI18next: async () => ({ t: (key: string) => key }),
}));
vi.mock('../ChapterSection', () => ({
  ChapterSection: ({
    chapter,
    visual,
    catalogExtra,
  }: {
    chapter: ChapterConfig;
    visual: ReactNode;
    catalogExtra?: ReactNode;
  }) => (
    <section id={chapter.anchor} aria-label={chapter.key}>
      {visual}
      {catalogExtra}
    </section>
  ),
}));
vi.mock('../../demo/ProductScene', () => ({
  ProductScene: ({ sceneId }: { sceneId: string }) => <div data-testid={`scene-${sceneId}`} />,
}));
vi.mock('../../ScreenshotsSection', () => ({
  ScreenshotsSection: ({ view }: { view: string }) => <div data-testid={`screenshot-${view}`} />,
}));
vi.mock('../SecurityDetail', () => ({ SecurityDetail: () => <div /> }));
vi.mock('../WorldPlaces', () => ({ WorldPlaces: () => <div data-testid="world-places" /> }));

import { EditorialChapters } from '../EditorialChapters';
import { CHAPTERS, WORLD_CHAPTER_ANCHOR } from '../chapters-data';

describe('EditorialChapters', () => {
  it('opens on the Tools, in their own capture, and numbers the others after them', async () => {
    render(await EditorialChapters({ lng: 'fr' }));

    const [first] = screen.getAllByRole('region');

    expect(first).toHaveAttribute('id', 'chapter-tools');
    expect(within(first!).getByTestId('screenshot-tools')).toBeInTheDocument();
    expect(CHAPTERS[0]?.num).toBe('01');
    expect(CHAPTERS.find(chapter => chapter.id === 'act')?.num).toBe('02');
    expect(CHAPTERS.at(-1)?.num).toBe('08');
  });

  it('shows each chapter its capture, and the others their scene', async () => {
    render(await EditorialChapters({ lng: 'fr' }));

    const shown = (key: ChapterConfig['key'], testId: string) =>
      within(screen.getByRole('region', { name: key })).getByTestId(testId);

    expect(shown('c1', 'screenshot-meetings')).toBeInTheDocument();
    expect(shown('c2', 'screenshot-relations')).toBeInTheDocument();
    expect(shown('c3', 'scene-watch')).toBeInTheDocument();
    expect(shown('c4', 'scene-call')).toBeInTheDocument();
    expect(shown('c5', 'screenshot-knowledge')).toBeInTheDocument();
  });

  it('files the detailed tools under their chapter, the overview first', () => {
    const tools = CHAPTERS.find(chapter => chapter.id === 'tools');
    const control = CHAPTERS.find(chapter => chapter.id === 'control');

    expect(tools?.catalog[0]).toBe('workbench');
    expect(control?.catalog).not.toContain('workbench');
  });

  it('keeps the connection relay separate from the new World screenshot and place directory', async () => {
    render(await EditorialChapters({ lng: 'fr' }));
    expect(screen.getAllByRole('region')).toHaveLength(CHAPTERS.length);
    const connections = screen.getByRole('region', { name: 'c6' });
    const world = screen.getByRole('region', { name: 'c7' });
    expect(connections).toHaveAttribute('id', 'chapter-connect');
    expect(within(connections).getByTestId('scene-relay')).toBeInTheDocument();
    expect(within(connections).queryByTestId('world-places')).toBeNull();
    expect(within(connections).getByRole('link')).toHaveAttribute(
      'href',
      `#${WORLD_CHAPTER_ANCHOR}`
    );
    expect(world).toHaveAttribute('id', WORLD_CHAPTER_ANCHOR);
    expect(within(world).getByTestId('screenshot-world')).toBeInTheDocument();
    expect(within(world).getByTestId('world-places')).toBeInTheDocument();
    expect(
      connections.compareDocumentPosition(world) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });
});

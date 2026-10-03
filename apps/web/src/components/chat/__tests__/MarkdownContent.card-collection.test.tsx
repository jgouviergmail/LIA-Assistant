/** Folding selected results must not fetch their media before opening. */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

afterEach(() => vi.unstubAllGlobals());

describe('deferred selected card collection', () => {
  it('reveals a history-search match inside a previously folded collection', () => {
    render(
      <MarkdownContent
        content='<details class="lia-card-collection" data-card-version="2"><summary>See more (1)</summary><div>Renewal reference</div></details>'
        searchHighlight="renewal"
      />
    );
    expect(screen.getByText('Renewal')).toBeVisible();
    expect(screen.getByText('Renewal').closest('details')).toHaveAttribute('open');
  });
  it.each(['See more (1)', 'Voir plus (1)'])(
    'opens %s without fetching hidden media',
    async label => {
      const requests: string[] = [];
      vi.stubGlobal(
        'Image',
        class {
          set src(value: string) {
            requests.push(value);
          }
        }
      );
      const { container } = render(
        <MarkdownContent
          content={
            `<details class="lia-card-collection" data-card-version="2"><summary>${label}</summary>` +
            '<div><p>Selected place</p><img class="lia-card-photo" src="/api/v1/connectors/google-places/photo/places/test/photos/test" alt="Place"></div></details>'
          }
        />
      );
      expect(requests).toHaveLength(0);
      expect(screen.queryByText('Selected place')).not.toBeInTheDocument();
      const summary = screen.getByText(label);
      expect(summary).toHaveAccessibleName(label);
      const details = container.querySelector('details');
      if (!details) throw new Error('Missing native disclosure');
      summary.focus();
      await act(async () => {
        details.open = true;
        fireEvent(details, new Event('toggle'));
      });
      expect(screen.getByText('Selected place')).toBeVisible();
      const image = screen.getByRole('img', { name: 'Place' });
      expect(image).toHaveAttribute('loading', 'lazy');
      fireEvent.load(image);
      expect(image).toHaveStyle({ opacity: '1' });
      expect(requests).toHaveLength(0);
      expect(summary).toHaveFocus();
      await act(async () => {
        details.open = false;
        fireEvent(details, new Event('toggle'));
      });
      await act(async () => {
        details.open = true;
        fireEvent(details, new Event('toggle'));
      });
      expect(screen.getByRole('img', { name: 'Place' })).toBe(image);
      expect(image).toHaveStyle({ opacity: '1' });
      expect(requests).toHaveLength(0);
    }
  );
});

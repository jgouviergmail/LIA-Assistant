import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ResultPreview } from '../ResultPreview';

describe('early result preview', () => {
  it('keeps exclusions and uncertainty inspectable and treats source text as text', async () => {
    const { user, container } = renderWithProviders(
      <ResultPreview
        collections={[
          {
            kind: 'EMAIL',
            candidate_count: 103,
            evaluated_count: 3,
            omitted_count: 100,
            items: [
              {
                id: '1',
                title: 'Contract',
                excerpt: '<script>attack()</script>',
                verdict: 'match',
              },
              { id: '2', title: 'Unsure', excerpt: 'Missing body', verdict: 'unknown' },
              { id: '3', title: 'Excluded', excerpt: 'Unrelated', verdict: 'non_match' },
            ],
          },
        ]}
      />
    );
    expect(screen.getByText('Contract')).toBeVisible();
    expect(screen.getByText('Unsure')).toBeVisible();
    expect(screen.getByText('Excluded')).not.toBeVisible();
    await user.click(screen.getByText('chat.result_preview.non_match', { selector: 'summary' }));
    expect(screen.getByText('Excluded')).toBeVisible();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('chat.result_preview.scope')).toBeVisible();
  });
});

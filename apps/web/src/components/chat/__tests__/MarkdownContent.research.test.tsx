/** Native numbering must survive sanitizing and rendering split research lists. */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

describe('research source numbering', () => {
  it('retains the source index and continuation after a rejected source or fold', () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<ol class="lia-research-list" start="5"><li value="6"><a href="https://sixth.example.test">Sixth source</a></li></ol>'
        }
      />
    );
    expect(container.querySelector('ol')).toHaveAttribute('start', '5');
    expect(container.querySelector('li')).toHaveAttribute('value', '6');
  });
});

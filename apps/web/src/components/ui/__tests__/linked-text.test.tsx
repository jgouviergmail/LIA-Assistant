import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LinkedText } from '../linked-text';

describe('LinkedText', () => {
  it('draws a written link by its host, in a page of its own', () => {
    render(<LinkedText text="Read [link](https://click.example.org/a?b=1) now" />);

    const link = screen.getByRole('link', { name: 'click.example.org' });

    expect(link).toHaveAttribute('href', 'https://click.example.org/a?b=1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByText(/\[link\]/)).toBeNull();
  });

  it('leaves a mail or a call to the system, not to a new page', () => {
    render(<LinkedText text="mailto:ana@example.org" />);

    expect(screen.getByRole('link')).not.toHaveAttribute('target');
  });

  it('shows where a link goes before it is followed', () => {
    render(<LinkedText text="[link](https://click.example.org/a?b=1)" />);

    expect(screen.getByRole('link')).toHaveAttribute(
      'title',
      'https://click.example.org/a?b=1'
    );
  });

  it('draws no link for an address that may not be followed', () => {
    const { container } = render(<LinkedText text="Open [link](javascript:alert(1)) here" />);

    expect(screen.queryByRole('link')).toBeNull();
    expect(container).toHaveTextContent('Open here');
  });

  it('keeps every word and line of the text', () => {
    const { container } = render(<LinkedText text={'One\nTwo https://example.org/a three'} />);

    expect(container.textContent).toBe('One\nTwo https://example.org/a three');
  });
});

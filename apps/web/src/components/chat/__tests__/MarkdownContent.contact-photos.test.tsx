/** API-rendered contact photos remain in their illustration slot. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const corpus = JSON.parse(
  readFileSync(
    join(process.cwd(), '../api/tests/unit/domains/agents/display/contact_card_corpus.json'),
    'utf8'
  )
) as { id: string; html: string; legacyHtml: string }[];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('MarkdownContent contact photos', () => {
  it.each(
    corpus.flatMap(item => [
      { id: item.id, version: 'current', html: item.html },
      { id: item.id, version: 'saved', html: item.legacyHtml },
    ])
  )('$version $id keeps the API card photo directly in its frame', ({ id, html }) => {
    const { container } = render(<MarkdownContent content={html} />);
    const slot = container.querySelector('.lia-card-top > .lia-illus');
    expect(slot).not.toBeNull();
    if (id === 'initials') {
      expect(slot).toHaveTextContent('LD');
      expect(slot?.querySelector('img')).toBeNull();
      return;
    }
    const image = slot?.querySelector('img');
    expect(image?.parentElement).toBe(slot);
    expect(image).toHaveAttribute('class', 'lia-illus__image');
    expect(image).toHaveAttribute('alt', '');
    expect(image).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(slot?.querySelector('button')).toBeNull();
  });

  it('loads a structured Google photo lazily through its authenticated DOM source', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.test:8000');
    const preloads: HTMLImageElement[] = [];
    vi.stubGlobal(
      'Image',
      class {
        constructor() {
          const image = document.createElement('img');
          preloads.push(image);
          return image;
        }
      }
    );
    const url = 'https://lh3.googleusercontent.com/contact-proxy-regression';
    const { container } = render(
      <MarkdownContent content={`<img class="lia-illus__image" src="${url}" alt="">`} />
    );
    const image = container.querySelector('img');
    expect(image).toHaveAttribute(
      'src',
      `https://api.example.test:8000/api/v1/auth/profile-image-proxy?url=${encodeURIComponent(url)}`
    );
    expect(image).toHaveAttribute('crossorigin', 'use-credentials');
    expect(image).toHaveAttribute('loading', 'lazy');
    expect(image).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(preloads).toHaveLength(0);
    expect(image).toHaveStyle({ opacity: 0 });
    fireEvent.load(image!);
    expect(image).toHaveStyle({ opacity: 1 });
  });

  it('keeps standalone Google profile photos expandable', () => {
    const { container, getByRole } = render(
      <MarkdownContent content="![Camille](https://lh3.googleusercontent.com/standalone-contact)" />
    );
    expect(container.querySelector('.contact-photo')).toHaveAttribute('alt', 'Camille');
    fireEvent.click(getByRole('button', { name: 'common.expand_image' }));
    expect(getByRole('dialog')).toBeInTheDocument();
  });

  it('does not turn illustrations outside a contact card into contact photos', () => {
    const { container } = render(
      <MarkdownContent content='<div class="lia-illus"><img src="https://images.example.test/diagram.png" alt="Diagram"></div>' />
    );
    expect(container.querySelector('img')).not.toHaveClass('lia-illus__image');
  });

  it('still sanitizes a saved contact photo before restoring its layout class', () => {
    const { container } = render(
      <MarkdownContent content='<div class="lia-contact"><div class="lia-illus"><img src="https://images.example.test/contact.png" alt="" onerror="alert(1)"><script>alert(2)</script></div></div>' />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).not.toHaveAttribute('onerror');
    expect(container.querySelector('img')?.parentElement).toHaveClass('lia-illus');
  });
});

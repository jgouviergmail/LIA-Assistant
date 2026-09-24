/**
 * The opening of a map page, and the product name in its title.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GradientTitle, MapsHero } from '../MapsHero';

describe('GradientTitle', () => {
  it('draws the product name in the gradient, wherever the language puts it', () => {
    const { container, rerender } = render(
      <GradientTitle text="Trois cartes pour comprendre LIA" />
    );
    expect(container.querySelector('.lm-grad')).toHaveTextContent('LIA');
    expect(container).toHaveTextContent('Trois cartes pour comprendre LIA');
    rerender(<GradientTitle text="LIA 能做什么" />);
    expect(container.firstChild?.textContent?.startsWith('LIA')).toBe(true);
    rerender(<GradientTitle text="Sans le nom" />);
    expect(container.querySelector('.lm-grad')).toBeNull();
  });
});

describe('MapsHero', () => {
  it('states what the page is, its counts and the version it describes', () => {
    render(
      <MapsHero
        eyebrow="Documentation vivante"
        title="L'histoire de LIA"
        lede="Chaque décision."
        stats={[
          { value: '310', label: 'décisions' },
          { value: '12', label: 'thèmes' },
        ]}
        stamp={{ version: 'Version 1.47.2', date: '24 septembre 2026', note: 'à jour' }}
      />
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent("L'histoire de LIA");
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('Version 1.47.2', { exact: false })).toBeInTheDocument();
  });
});

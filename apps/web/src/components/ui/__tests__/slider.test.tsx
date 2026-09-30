/**
 * Slider — the accessible name and spoken value land on the THUMB, the element
 * carrying `role="slider"`. An `aria-label` left on the Radix root names a
 * span no assistive technology reads, which is how the psyche sliders shipped
 * unnamed.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Slider } from '../slider';

describe('Slider', () => {
  it.each([
    ['en', 'Text size'],
    ['fr', 'Taille du texte'],
  ])('names its thumb from aria-label (%s)', (_lng, name) => {
    render(<Slider aria-label={name} value={[16]} min={14} max={20} step={1} />);
    expect(screen.getByRole('slider', { name })).toHaveAttribute('aria-valuenow', '16');
  });

  it('lets thumbProps name the thumb and speak its value', () => {
    render(
      <Slider
        value={[18]}
        min={14}
        max={20}
        step={1}
        thumbProps={{ 'aria-label': 'Taille du texte', 'aria-valuetext': '18 px (113 %)' }}
      />
    );
    expect(screen.getByRole('slider', { name: 'Taille du texte' })).toHaveAttribute(
      'aria-valuetext',
      '18 px (113 %)'
    );
  });
});

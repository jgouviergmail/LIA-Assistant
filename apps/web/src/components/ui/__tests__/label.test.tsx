/**
 * Label — the one primitive every label->control stack depends on.
 *
 * The `block` guard is a class-string oracle on purpose: jsdom performs no
 * layout, so the real behaviour (vertical margins actually pushing the control
 * down) cannot be measured here. It was measured in a real browser on
 * 2026-08-05: with the default `display: inline`, `margin-bottom` computed to
 * its full value yet the rendered label->control gap stayed ~3px whatever
 * `space-y-*` the wrapper carried — three successive canon recalibrations were
 * invisible on screen. This test pins the one class that keeps margins real.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Input } from '../input';
import { Label } from '../label';

describe('Label', () => {
  it('associates with its control through htmlFor', () => {
    // The design-system Input, not a native <input>: the a11y ratchet cannot
    // follow htmlFor from a component Label to a native sibling (the same
    // blind spot that killed the jsx-a11y component mapping), while the
    // rendered-DOM oracle below proves the association either way.
    renderWithProviders(
      <>
        <Label htmlFor="email">Email</Label>
        <Input id="email" />
      </>
    );
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('is block-level, so vertical stack margins actually apply', () => {
    renderWithProviders(<Label>Field name</Label>);
    expect(screen.getByText('Field name').className).toMatch(/\bblock\b/);
  });

  it('lets a caller opt into a horizontal layout (flex wins over block)', () => {
    renderWithProviders(<Label className="flex items-center">Row label</Label>);
    const className = screen.getByText('Row label').className;
    expect(className).toMatch(/\bflex\b/);
    // tailwind-merge must drop the conflicting base display, not stack both.
    expect(className).not.toMatch(/\bblock\b/);
  });
});

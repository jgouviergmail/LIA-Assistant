/**
 * `FormSection` — a named group of fields, with the theme icon its title owes.
 *
 * Two things it must do, and one it must not:
 *
 * - name the GROUP, not just draw a heading: a `fieldset`/`legend` pair makes
 *   the fields inside it a group assistive technology can announce, which is
 *   what a bare styled `<div>` cannot do;
 * - keep the icon decorative — it repeats the title, and announcing it twice
 *   is noise;
 * - never resolve a string itself. The primitive takes its title as a prop:
 *   it has no domain, so it has no vocabulary of its own (the `Skeleton` rule
 *   in `apps/web/CLAUDE.md`).
 */

import { render, screen } from '@testing-library/react';
import { Clock } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { FormSection } from '../form-section';

describe('FormSection', () => {
  it('names the group so its fields are announced together', () => {
    render(
      <FormSection icon={Clock} title="Quand">
        {/* `aria-label` rather than a `<label>` pair: `jsx-a11y` cannot
            follow `htmlFor` → `id`, a limit `apps/web/CLAUDE.md` records, and
            the ratchet covers test files too. The oracle here is the GROUP,
            not how this stand-in field is named. */}
        <input aria-label="Heure" />
      </FormSection>
    );
    const group = screen.getByRole('group', { name: 'Quand' });
    expect(group).toContainElement(screen.getByLabelText('Heure'));
  });

  it('shows the title to sighted readers too', () => {
    render(
      <FormSection icon={Clock} title="Quand">
        <span />
      </FormSection>
    );
    expect(screen.getByText('Quand')).toBeVisible();
  });

  it('keeps the icon out of the accessible name', () => {
    const { container } = render(
      <FormSection icon={Clock} title="Quand">
        <span />
      </FormSection>
    );
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    // The name is the title alone — no duplicated glyph label.
    expect(screen.getByRole('group', { name: 'Quand' })).toBeInTheDocument();
  });

  it('paints the icon in the theme colour, never grey', () => {
    // `apps/web/CLAUDE.md`: "A title always carries an icon, and a title icon
    // is never grey." The class is the oracle jsdom offers.
    const { container } = render(
      <FormSection icon={Clock} title="Quand">
        <span />
      </FormSection>
    );
    expect(container.querySelector('svg')!.getAttribute('class')).toContain('text-primary');
  });
});
